import sqlite3

import pytest

from app import app
from database.db import get_db


@pytest.fixture
def client(tmp_path):
    original = app.config.copy()
    app.config.update(TESTING=True, DATABASE=str(tmp_path / 'expenses.sqlite'), SECRET_KEY='test-only-key')
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
                  category='Food', currency='INR', amount='125.50')
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
    assert 'USD $ 0.30' in html
    assert 'CAD CA$ 10.00' in html
    assert 'INR ₹ 25.00' in html
    assert 'EUR € 2.00' in html
    submit(client, description='Earlier purchase', amount='100', expense_date='2026-08-01', currency='USD')
    html = client.get('/expenses?currency=USD&month=2026-09').get_data(as_text=True)
    assert 'USD $ 0.30' in html and 'Earlier purchase' not in html and 'CAD CA$ 10.00' not in html
    assert client.get('/expenses?month=invalid').status_code == 400
    assert client.get('/expenses?currency=FAKE').status_code == 400


def test_edit_delete_and_persistence(client):
    submit(client)
    expense_id = records()[0]['id']
    fields = dict(csrf_token=token(client), description='Train', expense_date='2026-09-27',
                  category='Transport', currency='CAD', amount='3.25')
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
