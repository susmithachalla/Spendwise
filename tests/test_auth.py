import re

import pytest
from werkzeug.security import check_password_hash

from src.app import app
from src.database.db import get_db


@pytest.fixture
def client(tmp_path):
    original = app.config.copy()
    app.config.update(REPORTING_RATE_PROVIDER=None, REPORTING_CURRENT_RATES={'INR':'80','USD':'1','CAD':'1.25','EUR':'0.8','JPY':'100','KWD':'0.25'}, TESTING=True, DATABASE=str(tmp_path / 'auth.sqlite'), SECRET_KEY='test-key')
    yield app.test_client()
    app.config.clear()
    app.config.update(original)


def submit(client, path, **fields):
    page = client.get(path).get_data(as_text=True)
    assert f'action="{path}"' in page
    token = re.search(r'name="csrf_token" value="([^"]+)"', page)[1]
    return client.post(path, data={'csrf_token': token, **fields})


def register(client, **overrides):
    fields = dict(name='Test Person', email='person@example.com', password='secure password')
    fields.update(overrides)
    return submit(client, '/register', **fields)


def logout(client):
    with client.session_transaction() as session:
        session['auth_csrf'] = 'logout-token'
    return client.post('/logout', data={'csrf_token': 'logout-token'})


def test_registration_login_and_workspace(client):
    client.get('/expenses/add')
    with client.session_transaction() as session:
        old_owner = session['expense_owner']
        token = session['expense_csrf']
    assert client.post('/expenses/add', data=dict(csrf_token=token, description='Private lunch',
        expense_date='2026-10-02', category='Groceries', currency='USD', amount='12')).status_code == 303
    response = register(client, email=' Person@Example.COM ')
    assert response.status_code == 303 and response.location == '/expenses'
    with app.app_context():
        user = get_db().execute('SELECT * FROM users').fetchone()
        assert user['email'] == 'person@example.com'
        assert user['password_hash'] != 'secure password'
        assert check_password_hash(user['password_hash'], 'secure password')
    with client.session_transaction() as session:
        assert session['user_id'] == user['id']
        assert session['expense_owner'] != old_owner
        assert 'expense_csrf' not in session
    assert b'Private lunch' in client.get('/expenses').data
    assert logout(client).status_code == 303
    assert b'Private lunch' not in client.get('/expenses').data
    other = app.test_client()
    assert submit(other, '/login', email='PERSON@example.com', password='secure password').location == '/expenses'
    assert b'Private lunch' in other.get('/expenses').data
    assert register(client, email='second@example.com').status_code == 303
    assert b'Private lunch' not in client.get('/expenses').data
    assert client.get('/expenses/1/edit').status_code == 404


@pytest.mark.parametrize('fields,message', [
    ({'name': ' '}, b'full name'),
    ({'email': 'bad'}, b'valid email'),
    ({'password': 'short'}, b'between 8 and 128'),
    ({'password': ' ' * 8}, b'between 8 and 128'),
    ({'password': 'x' * 129}, b'between 8 and 128'),
])
def test_invalid_registration(client, fields, message):
    response = register(client, **fields)
    assert response.status_code == 400 and message in response.data
    with app.app_context():
        assert get_db().execute('SELECT count(*) FROM users').fetchone()[0] == 0


def test_duplicate_and_bad_login(client):
    register(client)
    logout(client)
    response = register(client, email='PERSON@EXAMPLE.COM')
    assert response.status_code == 400 and b'already exists' in response.data
    for email, password in [('person@example.com', 'wrong'), ('missing@example.com', 'wrong'), ('', '')]:
        response = submit(client, '/login', email=email, password=password)
        assert response.status_code == 400
        with client.session_transaction() as session:
            assert 'user_id' not in session
    with app.app_context():
        assert get_db().execute('SELECT count(*) FROM users').fetchone()[0] == 1


@pytest.mark.parametrize('path', ['/login', '/register', '/logout'])
def test_csrf(client, path):
    assert client.post(path, data={}).status_code == 400
    assert client.post(path, data={'csrf_token': '€'}).status_code == 400


def test_errors_preserve_and_escape_fields(client):
    response = register(client, name='<script>alert(1)</script>', password='short')
    assert b'&lt;script&gt;' in response.data
    assert b'value="person@example.com"' in response.data
    assert b'value="short"' not in response.data
