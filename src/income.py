"""Opt-in, account-scoped income management and financial summaries."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from src.currencies import CURRENCIES, decimal_amount, money, parse_amount
from src.database.db import get_db
from src.periods import period_args

income_bp = Blueprint('income', __name__)
INCOME_CATEGORIES = dict(zip(
    ('Salary', 'Freelance', 'Business', 'Investments', 'Gifts', 'Other'),
    ({'color': color} for color in ('#743b50', '#668d87', '#c29557', '#807299', '#bc7182', '#6b819a'))))


def account():
    if not session.get('user_id'):
        return None
    return get_db().execute('SELECT * FROM users WHERE id=?', (session['user_id'],)).fetchone()


def enabled():
    user = account()
    if user is None:
        return False
    row = get_db().execute('SELECT income_enabled FROM account_preferences WHERE user_id=?',
                           (user['id'],)).fetchone()
    return bool(row and row['income_enabled'])


@income_bp.before_request
def protect_income():
    if account() is None:
        return redirect(url_for('login'))
    from src.expenses import prepare_workspace
    prepare_workspace()
    if request.endpoint != 'income.settings' and not enabled():
        legacy_edit = request.endpoint in ('income.edit', 'income.delete') and owned_income(request.view_args['income_id'])['category'] == 'Investments'
        if not legacy_edit:
            return redirect(url_for('expenses.index'))


@income_bp.post('/settings/income')
def settings():
    filters = period_args()
    value = request.form.get('enabled')
    if value not in ('0', '1'):
        abort(400)
    was_enabled = enabled()
    db = get_db()
    db.execute('''INSERT INTO account_preferences (user_id, income_enabled) VALUES (?, ?)
                  ON CONFLICT(user_id) DO UPDATE SET income_enabled=excluded.income_enabled''',
               (session['user_id'], int(value)))
    db.commit()
    if value == '1' and not was_enabled:
        return redirect(url_for('income.add', first=1, **filters), code=303)
    return redirect(url_for('expenses.overview', **filters), code=303)


def owned_income(income_id):
    row = get_db().execute('SELECT * FROM income WHERE id=? AND user_id=?',
                           (income_id, session['user_id'])).fetchone()
    if row is None:
        abort(404)
    return row


def income_form(existing=None):
    filters = period_args()
    first = existing is None and request.args.get('first') == '1'
    values = dict(amount='', currency=filters['currency'] or session.get('last_currency', 'INR'),
                  income_date=(filters['month'] + '-01') if filters['month'] else date.today().isoformat(),
                  category='', source='', notes='')
    if existing is not None:
        values.update(dict(existing))
        values['amount'] = str(decimal_amount(existing['amount_minor'], existing['fraction_digits']))
    errors = []
    if request.method == 'POST':
        values = {field: request.form.get(field, '').strip() for field in
                  ('amount', 'currency', 'income_date', 'category', 'source', 'notes')}
        if values['category'] not in INCOME_CATEGORIES or (values['category'] == 'Investments' and (existing is None or existing['category'] != 'Investments')):
            errors.append('Choose an income category from the list.')
        if len(values['source']) > 200:
            errors.append('Keep the payer name to 200 characters or fewer.')
        if len(values['notes']) > 2000:
            errors.append('Keep notes to 2,000 characters or fewer.')
        try:
            if date.fromisoformat(values['income_date']).isoformat() != values['income_date']:
                raise ValueError
        except ValueError:
            errors.append('Enter a valid income date.')
        try:
            minor, digits = parse_amount(values['amount'], values['currency'], allow_zero=True)
        except ValueError as error:
            errors.append(str(error))
        if not errors:
            db = get_db()
            fields = (values['income_date'], values['category'], values['source'], values['notes'],
                      minor, values['currency'], digits)
            if existing is None:
                db.execute('''INSERT INTO income (income_date, category, source, notes, amount_minor,
                              currency, fraction_digits, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                           fields + (session['user_id'],))
            else:
                db.execute('''UPDATE income SET income_date=?, category=?, source=?, notes=?,
                              amount_minor=?, currency=?, fraction_digits=? WHERE id=? AND user_id=?''',
                           fields + (existing['id'], session['user_id']))
            db.commit()
            flash('Income updated.' if existing is not None else 'Income saved.')
            return redirect(url_for('income.index', currency=values['currency'],
                                    month=values['income_date'][:7]), code=303)
    return render_template('income_form.html', values=values, errors=errors, first=first,
                           editing=existing is not None, currencies=CURRENCIES,
                           income_categories={k: v for k, v in INCOME_CATEGORIES.items() if k != "Investments" or (existing is not None and existing["category"] == "Investments")}, filters=filters), (400 if errors else 200)


@income_bp.route('/income/add', methods=['GET', 'POST'])
def add():
    return income_form()


@income_bp.route('/income/<int:income_id>/edit', methods=['GET', 'POST'])
def edit(income_id):
    return income_form(owned_income(income_id))


@income_bp.route('/income/<int:income_id>/delete', methods=['GET', 'POST'])
def delete(income_id):
    row = owned_income(income_id)
    filters = period_args()
    if request.method == 'POST':
        db = get_db()
        db.execute('DELETE FROM income WHERE id=? AND user_id=?', (income_id, session['user_id']))
        db.commit()
        flash('Income deleted.')
        return redirect(url_for('income.index', **filters), code=303)
    return render_template('income_delete.html', income=row, filters=filters)



@income_bp.get('/income')
def index():
    from src.expenses import dashboard_page
    return dashboard_page('income')
