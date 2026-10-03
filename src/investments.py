"""Account-scoped investment purchases, recorded at cash cost including fees."""
from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from src.currencies import CURRENCIES, decimal_amount, parse_amount
from src.database.db import get_db
from src.income import account
from src.periods import period_args
from src.reporting import INVESTMENT_SUBTYPES

investments_bp = Blueprint('investments', __name__)
TYPES = ('Stocks', 'ETFs', 'Mutual Funds', 'Other')


@investments_bp.before_request
def protect():
    if account() is None:
        return redirect(url_for('login'))
    from src.expenses import prepare_workspace
    prepare_workspace()


def owned(investment_id):
    row = get_db().execute('SELECT * FROM investments WHERE id=? AND user_id=?',
                           (investment_id, session['user_id'])).fetchone()
    if row is None:
        abort(404)
    return row


def form(existing=None):
    filters = period_args()
    values = dict(amount='', currency=filters['currency'] or 'INR',
                  investment_date=filters['month'] + '-01' if filters['month'] else date.today().isoformat(),
                  investment_type='', subtype='Contribution', notes='')
    if existing is not None:
        values.update(dict(existing))
        values['amount'] = str(decimal_amount(existing['amount_minor'], existing['fraction_digits']))
    errors = []
    if request.method == 'POST':
        values = {key: request.form.get(key, '').strip() for key in values if key in
                  ('amount', 'currency', 'investment_date', 'investment_type', 'subtype', 'notes')}
        values['subtype'] = request.form.get('subtype', 'Contribution').strip()
        if values['subtype'] not in INVESTMENT_SUBTYPES:
            errors.append('Choose an investment activity.')
        if values['investment_type'] not in TYPES:
            errors.append('Choose an investment type.')
        if len(values['notes']) > 2000:
            errors.append('Keep notes to 2,000 characters or fewer.')
        try:
            if date.fromisoformat(values['investment_date']).isoformat() != values['investment_date']:
                raise ValueError
        except ValueError:
            errors.append('Enter a valid investment date.')
        try:
            minor, digits = parse_amount(values['amount'], values['currency'])
        except ValueError as error:
            errors.append(str(error))
        if not errors:
            db = get_db()
            fields = (values['investment_date'], values['investment_type'], values['subtype'], values['notes'], minor, values['currency'], digits)
            if existing is None:
                db.execute('INSERT INTO investments (investment_date, investment_type, subtype, notes, amount_minor, currency, fraction_digits, user_id) VALUES (?,?,?,?,?,?,?,?)', fields + (session['user_id'],))
            else:
                db.execute('UPDATE investments SET investment_date=?, investment_type=?, subtype=?, notes=?, amount_minor=?, currency=?, fraction_digits=? WHERE id=? AND user_id=?', fields + (existing['id'], session['user_id']))
            db.commit()
            flash('Investment saved.')
            return redirect(url_for('investments.index', currency=values['currency'], month=values['investment_date'][:7]), code=303)
    return render_template('investment_form.html', values=values, types=TYPES, subtypes=INVESTMENT_SUBTYPES, currencies=CURRENCIES,
                           errors=errors, editing=existing is not None, filters=filters), (400 if errors else 200)


@investments_bp.route('/investments/add', methods=['GET', 'POST'])
def add():
    return form()


@investments_bp.route('/investments/<int:investment_id>/edit', methods=['GET', 'POST'])
def edit(investment_id):
    return form(owned(investment_id))


@investments_bp.route('/investments/<int:investment_id>/delete', methods=['GET', 'POST'])
def delete(investment_id):
    row = owned(investment_id)
    filters = period_args()
    if request.method == 'POST':
        db = get_db()
        db.execute('DELETE FROM investments WHERE id=? AND user_id=?', (investment_id, session['user_id']))
        db.commit()
        flash('Investment deleted.')
        return redirect(url_for('investments.index', **filters), code=303)
    return render_template('investment_delete.html', investment=row, filters=filters)


@investments_bp.get('/investments')
def index():
    from src.expenses import dashboard_page
    return dashboard_page('investments')
