import sqlite3
from decimal import Decimal
from urllib.parse import urlsplit, parse_qs

import pytest
from flask import template_rendered

from src.app import app
from src.database.db import get_db
from src.currencies import decimal_amount


@pytest.fixture
def client(tmp_path):
    original = app.config.copy()
    app.config.update(REPORTING_RATE_PROVIDER=None, REPORTING_CURRENT_RATES={'INR':'80','USD':'1','CAD':'1.25','EUR':'0.8','JPY':'100','KWD':'0.25'}, TESTING=True, DATABASE=str(tmp_path / 'income.sqlite'), SECRET_KEY='test-income')
    with app.app_context():
        db = get_db()
        for name in ['one', 'two']:
            db.execute('INSERT INTO users (name,email,password_hash,owner_token) VALUES (?,?,?,?)',
                       (name, name + '@example.com', 'unused', name))
        db.commit()
    browser = app.test_client()
    with browser.session_transaction() as session:
        session['user_id'] = 1
        session['expense_owner'] = 'one'
    yield browser
    app.config.clear()
    app.config.update(original)


def csrf(client):
    client.get('/expenses')
    with client.session_transaction() as session:
        return session['expense_csrf']


def toggle(client, value='1', query=''):
    return client.post('/settings/income' + query, data={'enabled': value, 'csrf_token': csrf(client)})


def save(client, path='/income/add', **overrides):
    fields = dict(amount='1000.50', currency='USD', income_date='2026-10-02', category='Salary',
                  csrf_token=csrf(client))
    fields.update(overrides)
    return client.post(path, data=fields)


def context(client, query=''):
    if 'currency=' not in query:
        query += ('&' if query else '?') + 'currency='
    if 'month=' not in query:
        query += ('&' if query else '?') + 'month='
    captured = []
    def capture(sender, template, context, **kwargs):
        captured.append(context)
    with template_rendered.connected_to(capture, app):
        response = client.get(('/income' if 'chart=income' in query else '/overview') + query)
    assert response.status_code == 200
    return captured[-1]


def rows():
    with app.app_context():
        return [dict(row) for row in get_db().execute('SELECT * FROM income ORDER BY id')]


def test_enable_skip_disable_and_account_preference(client):
    assert b'Enable income tracking' in client.get('/overview').data
    assert b'Income breakdown' not in client.get('/expenses?chart=income').data
    response = toggle(client, query='?currency=USD&month=2026-10')
    assert response.status_code == 303
    first = client.get(response.location)
    assert b'Add your first income' in first.data and b'Skip for now' in first.data
    assert b'Select a category' in first.data
    skipped = client.get('/overview?month=2026-10')
    assert b'No income added yet' in skipped.data and b'Spending breakdown' in client.get('/expenses').data
    ctx = context(client, '?currency=USD&month=2026-10')
    assert ctx['income_enabled'] and ctx['balances'] == []
    assert save(client).status_code == 303
    before = rows()
    assert toggle(client, '0').status_code == 303
    assert not context(client)['income_enabled']
    assert b'+ Add income' not in client.get('/expenses').data
    assert client.get('/income/add').status_code == 302
    assert save(client).status_code == 302
    assert rows() == before
    toggle(client)
    assert rows() == before and context(client)['income_enabled']
    restored = app.test_client()
    with restored.session_transaction() as session:
        session['user_id'] = 1
        session['expense_owner'] = 'one'
    assert context(restored)['income_enabled']


@pytest.mark.parametrize('optional', [{}, {'source': 'Example employer', 'notes': 'October salary\nBonus included'}])
def test_save_and_edit_optional_fields(client, optional):
    response = toggle(client)
    response = save(client, path=response.location, **optional)
    assert response.status_code == 303
    assert parse_qs(urlsplit(response.location).query) == {'currency': ['USD'], 'month': ['2026-10']}
    assert b'Income breakdown' in client.get(response.location).data
    row = rows()[0]
    assert row['source'] == optional.get('source', '') and row['notes'] == optional.get('notes', '')
    edit = client.get(f"/income/{row['id']}/edit")
    assert edit.status_code == 200
    assert row['source'].encode() in edit.data and row['notes'].encode() in edit.data
    assert save(client, path=f"/income/{row['id']}/edit", source='Client', notes='Project payment', category='Freelance', amount='10').status_code == 303
    updated = rows()[0]
    assert updated['source'] == 'Client' and updated['notes'] == 'Project payment'
    assert updated['category'] == 'Freelance' and updated['amount_minor'] == 1000
    assert client.get(f"/income/{row['id']}/delete").status_code == 200 and len(rows()) == 1
    assert client.post(f"/income/{row['id']}/delete", data={'csrf_token': csrf(client)}).status_code == 303
    assert rows() == []


def test_income_charts_and_balances(client):
    toggle(client)
    for code, amount, category in [('USD','100','Salary'), ('USD','0.10','Freelance'), ('USD','0.20','Freelance'), ('JPY','200','Gifts'), ('KWD','1.234','Other')]:
        assert save(client, currency=code, amount=amount, category=category).status_code == 303
    save(client, amount='9999', income_date='2026-09-01')
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO expenses (owner_token,expense_date,description,category,amount_minor,currency,fraction_digits) VALUES ('one','2026-10-03','Lunch','Groceries',12000,'USD',2)")
        db.commit()
    ctx = context(client, '?chart=income&month=2026-10')
    assert len(ctx['balances']) == 1
    usd = next(b for b in ctx['balances'] if b['currency'] == 'USD')
    assert usd['income'] == 'USD $ 107.24' and usd['expenses'] == 'USD $ 120.00' and usd['remaining'] == 'USD -$ 12.76'
    for chart in ctx['charts']:
        expected = sum((decimal_amount(r['amount_minor'], r['fraction_digits']) for r in ctx['reporting']['datasets']['income'] if r['currency'] == chart['currency']), Decimal(0))
        assert sum(Decimal(bar['amount']) for bar in chart['category']) == expected
        assert sum(Decimal(bar['amount']) for bar in chart['date']) == expected
    filtered = context(client, '?chart=income&currency=USD&month=2026-10&income_category=Freelance&category=Other')
    assert len(filtered['charts']) == 1 and filtered['charts'][0]['display'] == 'USD $ 0.30'
    assert filtered['balances'][0] == usd  # Category filters never distort account balances.
    assert context(client, '?month=2025-01')['balances'] == []
    save(client, currency='CAD', amount='0', income_date='2026-11-01')
    zero = context(client, '?chart=income&month=2026-11')
    assert zero['balances'][0]['income'] == zero['balances'][0]['remaining'] == 'CAD CA$ 0.00'
    assert zero['has_period_income'] and zero['charts'][0]['category'][0]['share'] == 0


@pytest.mark.parametrize('fields', [{'category':''}, {'category':'Food'}, {'amount':'-1'}, {'amount':'NaN'}, {'amount':'1.001'}, {'currency':'BAD'}, {'income_date':'2026-02-30'}, {'source':'x'*201}, {'notes':'x'*2001}])
def test_invalid_income(client, fields):
    toggle(client)
    assert save(client, **fields).status_code == 400
    assert not rows()


def test_isolation_csrf_and_escaping(client):
    toggle(client)
    save(client, source='<script>payer</script>', notes='<script>notes</script>')
    html = client.get('/income').data
    assert b'&lt;script&gt;notes' in html and b'<script>notes' not in html
    row = rows()[0]
    other = app.test_client()
    with other.session_transaction() as session:
        session['user_id'] = 2
        session['expense_owner'] = 'two'
    assert not context(other)['income_enabled']
    toggle(other)
    assert not context(other)['income_rows']
    for action in ['edit', 'delete']:
        path = f"/income/{row['id']}/{action}"
        assert other.get(path).status_code == 404
        assert other.post(path, data={'csrf_token': csrf(other)}).status_code == 404
        assert client.post(path, data={}).status_code == 400
    assert client.post('/settings/income', data={'enabled':'0'}).status_code == 400
    assert client.post('/income/add', data={}).status_code == 400
    anon = app.test_client()
    assert anon.get('/income/add').location == '/login'
    assert anon.post('/settings/income', data={'enabled':'1'}).location == '/login'
    assert len(rows()) == 1


def test_monthly_trends_and_invalid_filters(client):
    toggle(client)
    save(client, amount='10', income_date='2026-09-01')
    save(client, amount='20', income_date='2026-09-15')
    save(client, amount='40', income_date='2026-10-01')
    chart = context(client, '?chart=income')['charts'][0]
    assert [(bar['label'], Decimal(bar['amount'])) for bar in chart['month']] == [('2026-09', Decimal(30)), ('2026-10', Decimal(40))]
    for query in ['?month=invalid', '?income_category=invalid']:
        assert client.get(('/income' if 'income_category' in query else '/expenses') + query).status_code == (400 if 'income_category' in query else 303)


def test_three_pages_remember_filters_and_keep_content_separate(client):
    from html import unescape
    assert b'>Income</a>' not in client.get('/expenses').data
    assert client.get('/income').location == '/expenses'
    toggle(client)
    save(client, amount='250')
    expenses = client.get('/expenses?currency=USD&month=2026-10&category=Groceries')
    assert expenses.status_code == 200
    html = unescape(expenses.get_data(as_text=True))
    assert 'href="/overview?currency=USD&month=2026-10"' in html
    assert 'href="/income?currency=USD&month=2026-10"' in html
    assert 'Spending breakdown' in html and 'Income breakdown' not in html
    assert 'Saved income' not in html and 'Remaining cash' in html
    for path in ['/overview', '/income', '/expenses']:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'id="filter-currency"' not in html
        assert 'value="2026-10"' in html
    overview = client.get('/overview').data
    assert b'Remaining cash' in overview and b'USD $ 250.00' in overview
    assert b'Saved expenses' not in overview and b'Saved income' not in overview and b'chart-heading' not in overview
    income = client.get('/income').data
    assert b'Income breakdown' in income and b'Saved income' in income
    assert b'Saved expenses' not in income and b'Spending breakdown' not in income
    client.get('/income?currency=CAD&month=2026-09&income_category=Salary')
    html = client.get('/expenses').data
    assert b'id="filter-currency"' not in html and b'value="2026-09"' in html
    assert b'No matching expenses' in html
    client.get('/overview?currency=&month=')
    with client.session_transaction() as session:
        assert session['workspace_filters'] == {'month': ''}
    toggle(client, '0')
    assert b'>Income</a>' not in client.get('/overview').data
    assert len(rows()) == 1
