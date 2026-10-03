from decimal import Decimal
from urllib.error import URLError

import pytest
from src.app import app
from src.database.db import get_db
from test_income import client, toggle, save, context
from test_investments import invest


def expense(currency='INR', minor=8000, day='2026-10-02', category='Groceries', owner='one'):
    with app.app_context():
        db = get_db()
        db.execute('INSERT INTO expenses (owner_token,expense_date,description,category,amount_minor,currency,fraction_digits) VALUES (?,?,?,?,?,?,2)',
                   (owner,day,'Original transaction',category,minor,currency))
        db.commit()


def test_single_currency_never_calls_provider(client):
    def fail(*args):
        pytest.fail('Single-currency reports must not request exchange rates')
    app.config['REPORTING_RATE_PROVIDER'] = fail
    expense()
    report = context(client, '?month=2026-10')
    assert not report['reporting']['isMultiCurrency']
    assert report['selected'] == 'INR'
    assert report['balances'][0]['expenses'] == 'INR ₹ 80.00'
    with app.app_context():
        assert not get_db().execute('SELECT * FROM reporting_conversions').fetchall()
    expense(currency='USD', day='2026-09-02')
    assert context(client, '?month=2026-09')['selected'] == 'USD'
    assert context(client, '?month=2020-01')['selected'] == ''


def test_historical_normalization_audit_and_no_double_conversion(client):
    calls=[]
    def rate(code, day):
        calls.append((code, day))
        return Decimal('80'), day, 'Test historical'
    app.config['REPORTING_RATE_PROVIDER'] = rate
    toggle(client)
    expense(minor=800000) # INR 8,000 -> USD 100
    save(client, amount='1000')
    invest(client, amount='1600', currency='INR') # USD 20
    first = context(client, '?month=2026-10')
    assert first['reporting']['isMultiCurrency'] and first['selected'] == 'USD'
    assert first['balances'][0]['remaining'] == 'USD $ 880.00'
    assert first['balances'][0]['expenses'] == 'USD $ 100.00'
    assert first['balances'][0]['investments'] == 'USD $ 20.00'
    assert calls == [('INR','2026-10-02')]
    assert context(client, '?month=2026-10')['balances'] == first['balances']
    with app.app_context():
        db=get_db()
        assert db.execute('SELECT amount_minor,currency FROM expenses').fetchone()[:] == (800000,'INR')
        audit = db.execute("SELECT * FROM reporting_conversions WHERE kind='expenses'").fetchone()
        assert (audit['original_minor'], audit['units_per_usd'], audit['usd_minor']) == ('800000','80','10000')
        db.execute('UPDATE expenses SET amount_minor=1600000')
        db.commit()
    assert context(client, '?month=2026-10')['balances'][0]['expenses'] == 'USD $ 200.00'
    assert calls == [('INR','2026-10-02')]
    with app.app_context():
        assert get_db().execute("SELECT count(*) FROM reporting_conversions WHERE kind='expenses'").fetchone()[0] == 2


def test_categories_do_not_change_currency_mode_and_accounts_isolated(client):
    expense(currency='USD', minor=100, category='Groceries')
    expense(currency='INR', minor=8000, category='Dining & Drinks')
    response = client.get('/expenses?month=2026-10&category=Groceries')
    assert b'Multiple currencies detected' in response.data
    assert b'Spending breakdown' in response.data and b'USD $ 1.00' in response.data
    other=app.test_client()
    with other.session_transaction() as session:
        session['user_id']=2
        session['expense_owner']='two'
    expense(currency='INR', owner='two')
    assert context(other, '?month=2026-10')['selected'] == 'INR'
    with app.app_context():
        db=get_db(); db.execute("DELETE FROM expenses WHERE currency='USD'"); db.commit()
    result=context(client, '?month=2026-10')
    assert result['selected']=='INR' and not result['reporting']['isMultiCurrency']


def test_rate_failure_and_current_fallback(client):
    def offline(*args):
        raise URLError('offline')
    app.config.update(REPORTING_RATE_PROVIDER=offline, REPORTING_CURRENT_RATES={})
    expense()
    expense(currency='USD')
    failed=context(client, '?month=2026-10')
    assert failed['reporting']['error'] and not failed['charts']
    assert len(failed['expenses']) == 2 and failed['balances'][0]['expenses'] == '—'
    app.config['REPORTING_CURRENT_RATES']={'INR':'80'}
    recovered=context(client, '?month=2026-10')
    assert recovered['reporting']['error'] is None
    assert recovered['balances'][0]['expenses']=='USD $ 81.00'


def test_zero_and_rounding_consistent_with_charts(client):
    toggle(client)
    save(client, amount='0', currency='USD')
    expense(minor=40)  # INR .40 /80 -> USD .005 -> .01 half-up
    result=context(client, '?month=2026-10')
    assert result['balances'][0]['remaining']=='USD -$ 0.01'
    assert result['charts'][0]['display']=='USD $ 0.01'


def test_inr_only_category_keeps_period_reporting_currency(client):
    from flask import template_rendered
    expense(currency='USD', minor=1000, category='Groceries')
    expense(currency='INR', minor=8000, category='Dining & Drinks')
    expense(currency='JPY', minor=10000, day='2026-09-02')
    baseline = context(client, '?month=2026-10')
    captured = []
    def capture(sender, template, context, **kwargs):
        captured.append(context)
    with template_rendered.connected_to(capture, app):
        response = client.get('/expenses?month=2026-10&category=Dining+%26+Drinks')
    assert response.status_code == 200
    filtered = captured[-1]
    assert filtered['reporting']['isMultiCurrency']
    assert filtered['selected'] == 'USD'
    assert filtered['balances'] == baseline['balances']
    assert filtered['balances'][0]['expenses'] == 'USD $ 11.00'
    assert {row['currency'] for row in filtered['expenses']} == {'INR'}
    assert len(filtered['charts']) == 1
    assert filtered['charts'][0]['currency'] == 'USD'
    assert filtered['charts'][0]['display'] == 'USD $ 1.00'
    assert context(client, '?month=2026-09')['selected'] == 'JPY'
