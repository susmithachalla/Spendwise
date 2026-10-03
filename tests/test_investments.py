from test_income import client, csrf, toggle, save, context
from src.app import app
from src.database.db import get_db


def invest(client, path='/investments/add', **overrides):
    fields = dict(csrf_token=csrf(client), amount='200.25', currency='USD',
                  investment_date='2026-10-02', investment_type='Stocks', notes='ABC including fees')
    fields.update(overrides)
    return client.post(path, data=fields)


def test_investment_crud_and_remaining(client):
    toggle(client)
    save(client, amount='1000')
    assert client.get('/investments/add').status_code == 200
    assert invest(client).status_code == 303
    assert invest(client, currency='JPY', amount='500', investment_type='ETFs', notes='').status_code == 303
    ctx = context(client, '?currency=USD&month=2026-10')
    assert ctx['balances'][0]['investments'] == 'USD $ 205.25'
    assert ctx['balances'][0]['remaining'] == 'USD $ 794.75'
    assert ctx['balances'][0]['expenses'] == 'USD $ 0.00'
    row = next(r for r in ctx['investment_rows'] if r['currency'] == 'USD')
    assert client.get(f"/investments/{row['id']}/edit").status_code == 200
    assert invest(client, path=f"/investments/{row['id']}/edit", amount='1200', investment_type='Mutual Funds').status_code == 303
    assert context(client, '?currency=USD&month=2026-10')['balances'][0]['remaining'] == 'USD -$ 205.00'
    toggle(client, '0')
    balance = context(client, '?currency=USD&month=2026-10')['balances'][0]
    assert balance['investments'] == 'USD $ 1,205.00' and balance['remaining'] == '-'
    toggle(client)
    assert client.get(f"/investments/{row['id']}/delete").status_code == 200
    assert client.post(f"/investments/{row['id']}/delete", data={'csrf_token':csrf(client)}).status_code == 303
    assert context(client, '?currency=USD&month=2026-10')['balances'][0]['remaining'] == 'USD $ 995.00'
    assert context(client, '?currency=JPY&month=2026-10')['balances'][0]['investments'] == 'USD $ 5.00'


def test_investment_validation_and_isolation(client):
    for fields in [{'investment_type':''}, {'investment_type':'Salary'}, {'amount':'0'}, {'amount':'NaN'}, {'amount':'1.001'}, {'investment_date':'bad'}, {'notes':'x'*2001}]:
        assert invest(client, **fields).status_code == 400
    assert invest(client, notes='').status_code == 303
    with app.app_context():
        row = get_db().execute('SELECT * FROM investments').fetchone()
        assert row['notes'] == ''
    other = app.test_client()
    with other.session_transaction() as session:
        session['user_id'] = 2
        session['expense_owner'] = 'two'
    assert not context(other)['investment_rows']
    for action in ['edit', 'delete']:
        path = f"/investments/{row['id']}/{action}"
        assert other.get(path).status_code == 404
        assert other.post(path, data={'csrf_token':csrf(other)}).status_code == 404
        assert client.post(path, data={}).status_code == 400
    assert app.test_client().get('/investments/add').location == '/login'


def test_returns_and_contributions_share_reporting(client):
    from test_reporting import expense
    toggle(client)
    save(client, amount='5000')
    invest(client, amount='500', subtype='Contribution')
    invest(client, amount='100', subtype='Dividend')
    expense(currency='USD', minor=100000)
    ctx = context(client, '?month=2026-10')
    balance = ctx['balances'][0]
    assert balance['income'] == 'USD $ 5,100.00'
    assert balance['investments'] == 'USD $ 500.00'
    assert balance['expenses'] == 'USD $ 1,000.00'
    assert balance['remaining'] == 'USD $ 3,600.00'
    assert len(ctx['income_rows']) == 1
    assert len(ctx['investment_rows']) == 2
    assert b'Dividend' in client.get('/investments?subtype=Dividend').data
    assert client.get('/investments?subtype=invalid').status_code == 400
    assert invest(client, subtype='invalid').status_code == 400
    row = next(r for r in ctx['investment_rows'] if r['subtype'] == 'Contribution')
    invest(client, path=f"/investments/{row['id']}/edit", amount='500', subtype='Withdrawal')
    balance = context(client, '?month=2026-10')['balances'][0]
    assert balance['investments'] == 'USD $ 0.00'
    assert balance['income'] == 'USD $ 5,600.00'


def test_legacy_returns_and_multi_currency(client):
    with app.app_context():
        db = get_db()
        db.execute("INSERT INTO income (user_id,income_date,category,source,amount_minor,currency,fraction_digits) VALUES (1,'2026-10-02','Investments','Legacy dividend',8000,'INR',2)")
        db.commit()
    invest(client, amount='10', subtype='Contribution')
    ctx = context(client, '?month=2026-10')
    assert ctx['balances'][0]['income'] == 'USD $ 1.00'
    assert ctx['balances'][0]['remaining'] == 'USD -$ 9.00'
    legacy = next(r for r in ctx['investment_rows'] if r['storage_kind'] == 'income')
    assert legacy['amount_minor'] == 8000 and legacy['currency'] == 'INR'
    assert legacy['subtype'] == 'Return'
    assert client.get('/investments').status_code == 200
    assert client.get(f"/income/{legacy['id']}/edit").status_code == 200
    assert not ctx['income_rows']


def test_all_cash_received_subtypes_and_income_chart(client):
    toggle(client)
    for subtype in ('Return', 'Withdrawal', 'Dividend', 'Interest', 'Capital gain', 'Other income'):
        assert invest(client, amount='10', currency='INR', subtype=subtype).status_code == 303
    ctx = context(client, '?chart=income&month=2026-10&income_category=Investments')
    assert ctx['selected'] == 'INR'
    assert ctx['balances'][0]['income'] == 'INR ₹ 60.00'
    assert ctx['balances'][0]['investments'] == 'INR ₹ 0.00'
    assert ctx['charts'][0]['display'] == 'INR ₹ 60.00'
    assert not ctx['income_rows']
    assert save(client, category='Investments').status_code == 400
