import sqlite3

import pytest

from src.app import app
from src.database.db import get_db


@pytest.fixture
def client(tmp_path):
    original = app.config.copy()
    app.config.update(REPORTING_RATE_PROVIDER=None, REPORTING_CURRENT_RATES={'INR':'80','USD':'1','CAD':'1.25','EUR':'0.8','JPY':'100','KWD':'0.25'}, TESTING=True, DATABASE=str(tmp_path / 'expenses.sqlite'), SECRET_KEY='test-only-key')
    with app.app_context():
        get_db()
    with app.test_client() as browser:
        yield browser
    app.config.clear()
    app.config.update(original)


def token(client):
    client.get('/expenses/add')
    with client.session_transaction() as session:
        return session['expense_csrf']


def submit(client, **overrides):
    fields = dict(csrf_token=token(client), description='Lunch', expense_date='2026-09-28',
                  category='Groceries', currency='INR', amount='125.50')
    fields.update(overrides)
    return client.post('/expenses/add', data=fields)


def records():
    with sqlite3.connect(app.config['DATABASE']) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute('SELECT * FROM expenses ORDER BY id').fetchall()


@pytest.mark.parametrize('code,raw,expected,digits', [
    ('INR', '125.50', 12550, 2), ('USD', '0.10', 10, 2),
    ('EUR', '12.34', 1234, 2), ('CAD', '15.99', 1599, 2),
    ('JPY', '125', 125, 0), ('KWD', '1.234', 1234, 3),
])
def test_currency_roundtrip(client, code, raw, expected, digits):
    assert submit(client, currency=code, amount=raw).status_code == 303
    row = records()[0]
    assert (row['currency'], row['amount_minor'], row['fraction_digits']) == (code, expected, digits)
    assert code in client.get('/expenses').get_data(as_text=True)
    page = client.get(f"/expenses/{row['id']}/edit").get_data(as_text=True)
    assert f'value="{code}"' in page
    assert f'value="{raw}"' in page


@pytest.mark.parametrize('raw,code', [
    ('0', 'USD'), ('-1', 'USD'), ('NaN', 'USD'), ('Infinity', 'USD'),
    ('1e10', 'USD'), ('1,200.00', 'USD'), ('1.001', 'EUR'),
    ('1.5', 'JPY'), ('1.2345', 'KWD'), ('1', 'FAKE'),
    ('999999999999999999999999', 'USD'), ('', 'CAD'),
])
def test_invalid_money_is_not_saved(client, raw, code):
    response = submit(client, currency=code, amount=raw)
    assert response.status_code == 400
    assert not records()
    assert 'Check your expense' in response.get_data(as_text=True)


def test_separate_exact_totals_and_filters(client):
    for amount, code in [('0.10', 'USD'), ('0.20', 'USD'), ('10', 'CAD'), ('25', 'INR'), ('2', 'EUR')]:
        submit(client, amount=amount, currency=code)
    html = client.get('/expenses').get_data(as_text=True)
    assert 'USD $ 11.11' in html
    assert 'CAD CA$ 10.00' in html
    assert 'INR ₹ 25.00' in html
    assert 'EUR € 2.00' in html
    submit(client, description='Earlier purchase', amount='100', expense_date='2026-08-01', currency='USD')
    html = client.get('/expenses?currency=USD&month=2026-09').get_data(as_text=True)
    assert 'USD $ 11.11' in html and 'Earlier purchase' not in html and 'CAD CA$ 10.00' in html
    assert client.get('/expenses?month=invalid').status_code == 303
    assert client.get('/expenses?currency=FAKE').status_code == 200


def test_edit_delete_and_persistence(client):
    submit(client)
    expense_id = records()[0]['id']
    fields = dict(csrf_token=token(client), description='Train', expense_date='2026-09-27',
                  category='Transportation', currency='CAD', amount='3.25')
    assert client.post(f'/expenses/{expense_id}/edit', data=fields).status_code == 303
    row = records()[0]
    assert (row['description'], row['currency'], row['amount_minor']) == ('Train', 'CAD', 325)
    assert 'CAD CA$ 3.25' in client.get('/expenses').get_data(as_text=True)
    # A new client with the same signed cookie can retrieve persisted data.
    restored = app.test_client()
    cookie = client.get_cookie(app.config['SESSION_COOKIE_NAME'])
    restored.set_cookie(app.config['SESSION_COOKIE_NAME'], cookie.value)
    assert 'Train' in restored.get('/expenses').get_data(as_text=True)
    assert client.get(f'/expenses/{expense_id}/delete').status_code == 200
    assert len(records()) == 1  # GET is confirmation only.
    assert client.post(f'/expenses/{expense_id}/delete', data={'csrf_token': token(client)}).status_code == 303
    assert not records()


def test_browser_isolation_and_csrf(client):
    submit(client, description='Private purchase')
    expense_id = records()[0]['id']
    other = app.test_client()
    assert 'Private purchase' not in other.get('/expenses').get_data(as_text=True)
    for action in ['edit', 'delete']:
        assert other.get(f'/expenses/{expense_id}/{action}').status_code == 404
        assert other.post(f'/expenses/{expense_id}/{action}', data={'csrf_token': token(other)}).status_code == 404
    for bad in ['', 'wrong', '€']:
        assert client.post(f'/expenses/{expense_id}/delete', data={'csrf_token': bad}).status_code == 400
    assert client.post('/expenses/add', data={}).status_code == 400
    assert len(records()) == 1


def test_validation_and_escaping(client):
    assert submit(client, expense_date='2026-02-30').status_code == 400
    assert submit(client, category='fake').status_code == 400
    assert submit(client, description=' ').status_code == 400
    assert not records()
    assert submit(client, description='<script>alert(1)</script>').status_code == 303
    html = client.get('/expenses').get_data(as_text=True)
    assert '&lt;script&gt;' in html and '<script>alert(1)</script>' not in html


def test_existing_pages_and_links(client):
    for path in ['/', '/login', '/register', '/terms', '/privacy', '/expenses', '/expenses/add']:
        response = client.get(path)
        assert response.status_code == 200
        assert 'href="/expenses"' in response.get_data(as_text=True)
    for path in ['/static/css/expenses.css', '/static/js/expenses.js']:
        assert client.get(path).status_code == 200


def chart_context(client, path='/expenses'):
    from flask import template_rendered
    captured = []

    def capture(sender, template, context, **extra):
        captured.append(context)

    with template_rendered.connected_to(capture, app):
        response = client.get(path)
    assert response.status_code == 200
    return captured[0]


def test_chart_totals_match_filtered_rows(client):
    from collections import defaultdict
    from decimal import Decimal
    from src.currencies import decimal_amount

    for fields in [
        dict(amount='0.10', currency='USD', category='Groceries'),
        dict(amount='0.20', currency='USD', category='Groceries'),
        dict(amount='4', currency='USD', category='Transportation', expense_date='2026-09-27'),
        dict(amount='20', currency='USD', expense_date='2026-08-01'),
        dict(amount='3.125', currency='KWD'),
        dict(amount='500', currency='JPY'),
    ]:
        assert submit(client, **fields).status_code == 303
    for query in ['', '?month=2026-09', '?currency=USD', '?currency=USD&month=2026-09']:
        context = chart_context(client, '/expenses' + query)
        expected = defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
        for row in context['reporting']['datasets']['expenses']:
            amount = decimal_amount(row['amount_minor'], row['fraction_digits'])
            expected[row['currency']]['category'][row['category']] += amount
            expected[row['currency']]['date'][row['expense_date']] += amount
        assert {chart['currency'] for chart in context['charts']} == set(expected)
        for chart in context['charts']:
            for mode in ['category', 'date']:
                assert {bar['label']: Decimal(bar['amount']) for bar in chart[mode]} == expected[chart['currency']][mode]
                assert max(bar['width'] for bar in chart[mode]) == 100
            assert chart['display'] == next(s['display'] for s in context['summaries'] if s['currency'] == chart['currency'])
            assert [bar['label'] for bar in chart['date']] == sorted(expected[chart['currency']]['date'])
    usd = chart_context(client, '/expenses?currency=USD&month=2026-09')['charts'][0]
    assert usd['category'][0]['display'] == 'USD $ 17.80'
    assert chart_context(app.test_client())['charts'] == []
    empty = client.get('/expenses?month=2020-01')
    assert b'No spending to chart' in empty.data
    assert chart_context(client, '/expenses?month=2020-01')['charts'] == []


def test_charts_refresh_after_mutations(client):
    submit(client, currency='USD', amount='10')
    row = records()[0]
    assert chart_context(client)['charts'][0]['display'] == 'USD $ 10.00'
    fields = dict(csrf_token=token(client), description='Changed', expense_date='2026-09-29',
                  category='Transportation', currency='JPY', amount='200')
    assert client.post(f"/expenses/{row['id']}/edit", data=fields).status_code == 303
    chart = chart_context(client)['charts'][0]
    assert chart['currency'] == 'JPY' and chart['category'][0]['label'] == 'Transportation'
    assert chart['display'] == 'JPY ¥ 200'
    assert client.post(f"/expenses/{row['id']}/delete", data={'csrf_token': token(client)}).status_code == 303
    assert chart_context(client)['charts'] == []


def test_doughnut_shares_and_column_scale(client):
    from decimal import Decimal
    for category, amount in [('Groceries', '25'), ('Transportation', '75')]:
        submit(client, category=category, amount=amount, currency='USD')
    chart = chart_context(client)['charts'][0]
    assert [bar['percent'] for bar in chart['category']] == ['25.0', '75.0']
    assert sum(bar['share'] for bar in chart['category']) == 100
    assert chart['category'][1]['offset'] == -25
    assert len({bar['color'] for bar in chart['category']}) == 2
    assert chart['ticks'] == ['USD $ 100.00', 'USD $ 75.00', 'USD $ 50.00', 'USD $ 25.00', 'USD $ 0.00']
    assert chart['date'][0]['height'] == 100
    assert sum(Decimal(bar['amount']) for bar in chart['category']) == Decimal(chart['date'][0]['amount'])


def test_new_categories_and_combined_filters(client):
    from src.categories import CATEGORIES
    page = client.get('/expenses/add').get_data(as_text=True)
    assert 'disabled selected>Select a category' in page
    assert '<optgroup label="Food &amp; drinks">' in page
    assert submit(client, category='').status_code == 400
    assert submit(client, category='Food').status_code == 400
    for category in CATEGORIES:
        assert submit(client, category=category, currency='USD', amount='10').status_code == 303
    chart = chart_context(client)['charts'][0]
    assert {bar['label'] for bar in chart['category']} == set(CATEGORIES)
    assert len({bar['color'] for bar in chart['category']}) == len(CATEGORIES)
    context = chart_context(client, '/expenses?category=Dining+%26+Drinks&currency=USD&month=2026-09')
    assert len(context['expenses']) == 1
    assert context['charts'][0]['category'][0]['label'] == 'Dining & Drinks'
    assert context['charts'][0]['display'] == 'USD $ 10.00'
    assert client.get('/expenses?category=made-up').status_code == 400


def test_category_migration_and_legacy_edit(client):
    submit(client)
    with client.session_transaction() as session:
        owner = session['expense_owner']
    with sqlite3.connect(app.config['DATABASE']) as db:
        for category in ['Transport', 'Health', 'Shopping', 'Food', 'Bills']:
            db.execute('''INSERT INTO expenses (owner_token, expense_date, description, category,
                       amount_minor, currency, fraction_digits) VALUES (?, '2026-09-28', ?, ?, 1234, 'USD', 2)''',
                       (owner, category, category))
    before = records()
    client.get('/expenses')
    after = records()
    mapping = {'Transport': 'Transportation', 'Health': 'Health & Wellness', 'Shopping': 'Shopping & Personal Care'}
    for original, migrated in zip(before, after):
        expected = dict(original)
        expected['category'] = mapping.get(original['category'], original['category'])
        assert dict(migrated) == expected
    client.get('/expenses')
    assert [dict(row) for row in records()] == [dict(row) for row in after]
    food = next(row for row in after if row['category'] == 'Food')
    page = client.get(f"/expenses/{food['id']}/edit").get_data(as_text=True)
    assert 'selected>Food (existing)' in page
    fields = dict(csrf_token=token(client), description='Updated', expense_date='2026-09-28',
                  category='Food', currency='USD', amount='12.34')
    assert client.post(f"/expenses/{food['id']}/edit", data=fields).status_code == 303
    fields['category'] = 'Bills'
    assert client.post(f"/expenses/{food['id']}/edit", data=fields).status_code == 400
    fields['category'] = 'Dining & Drinks'
    assert client.post(f"/expenses/{food['id']}/edit", data=fields).status_code == 303
    context = chart_context(client, '/expenses?category=Dining+%26+Drinks')
    assert context['charts'][0]['display'] == 'USD $ 12.34'
    assert chart_context(client, '/expenses?category=Bills')['expenses'][0]['category'] == 'Bills'
    assert client.get('/expenses?category=Transport').status_code == 200
