"""Expense routes scoped to an anonymous browser workspace until accounts exist."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from currencies import CURRENCIES, decimal_amount, money, parse_amount
from database.db import get_db

expenses_bp = Blueprint('expenses', __name__)
CATEGORIES = ('Food', 'Housing', 'Transport', 'Bills', 'Health', 'Shopping', 'Entertainment', 'Other')


@expenses_bp.before_request
def prepare_workspace():
    if 'expense_owner' not in session:
        session['expense_owner'] = secrets.token_urlsafe(32)
        session.permanent = True
    if 'expense_csrf' not in session:
        session['expense_csrf'] = secrets.token_urlsafe(32)
    if request.method == 'POST':
        provided = request.form.get('csrf_token', '')
        if not secrets.compare_digest(provided.encode('utf-8'), session['expense_csrf'].encode('utf-8')):
            abort(400, description='This form has expired. Reload the page and try again.')


def owned_expense(expense_id):
    row = get_db().execute('SELECT * FROM expenses WHERE id = ? AND owner_token = ?',
                           (expense_id, session['expense_owner'])).fetchone()
    if row is None:
        abort(404)
    return row


@expenses_bp.get('/expenses')
def index():
    selected = request.args.get('currency', '')
    month = request.args.get('month', '')
    rows = get_db().execute('SELECT * FROM expenses WHERE owner_token = ? ORDER BY expense_date DESC, id DESC',
                            (session['expense_owner'],)).fetchall()
    available = sorted({row['currency'] for row in rows})
    if selected and selected not in CURRENCIES and selected not in available:
        abort(400, description='Unknown currency filter.')
    if month:
        try:
            parsed = date.fromisoformat(month + '-01')
            if parsed.strftime('%Y-%m') != month:
                raise ValueError
        except ValueError:
            abort(400, description='Choose a valid month.')
    rows = [row for row in rows if (not selected or row['currency'] == selected)
            and (not month or row['expense_date'].startswith(month))]
    # Decimal totals also handle stored currency precision if metadata later changes.
    totals = defaultdict(Decimal)
    precisions = {}
    for row in rows:
        code = row['currency']
        totals[code] += decimal_amount(row['amount_minor'], row['fraction_digits'])
        precisions[code] = max(precisions.get(code, 0), row['fraction_digits'])
    summaries = [{'currency': code, 'display': money(int(total.scaleb(precisions[code])), code, precisions[code])}
                 for code, total in sorted(totals.items())]
    return render_template('expenses.html', expenses=rows, summaries=summaries,
                           available=available, selected=selected, month=month)


def expense_form(existing=None):
    values = {'expense_date': date.today().isoformat(), 'description': '', 'category': 'Other',
              'currency': session.get('last_currency', 'INR'), 'amount': ''}
    if existing is not None:
        values.update(dict(existing))
        values['amount'] = str(decimal_amount(existing['amount_minor'], existing['fraction_digits']))
    errors = []
    if request.method == 'POST':
        values = {key: request.form.get(key, '').strip() for key in
                  ('expense_date', 'description', 'category', 'currency', 'amount')}
        if not 1 <= len(values['description']) <= 200:
            errors.append('Enter a description between 1 and 200 characters.')
        if values['category'] not in CATEGORIES:
            errors.append('Choose a category from the list.')
        try:
            parsed = date.fromisoformat(values['expense_date'])
            if parsed.isoformat() != values['expense_date']:
                raise ValueError
        except ValueError:
            errors.append('Enter a valid expense date.')
        try:
            minor, digits = parse_amount(values['amount'], values['currency'])
        except ValueError as error:
            errors.append(str(error))
        if not errors:
            db = get_db()
            fields = (values['expense_date'], values['description'], values['category'],
                      minor, values['currency'], digits)
            if existing is None:
                db.execute('''INSERT INTO expenses
                    (expense_date, description, category, amount_minor, currency, fraction_digits, owner_token)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''', fields + (session['expense_owner'],))
            else:
                db.execute('''UPDATE expenses SET expense_date=?, description=?, category=?,
                    amount_minor=?, currency=?, fraction_digits=? WHERE id=? AND owner_token=?''',
                           fields + (existing['id'], session['expense_owner']))
            db.commit()
            session['last_currency'] = values['currency']
            flash('Expense updated.' if existing is not None else 'Expense saved.')
            return redirect(url_for('expenses.index'), code=303)
    return render_template('expense_form.html', values=values, errors=errors,
                           currencies=CURRENCIES, categories=CATEGORIES,
                           editing=existing is not None), (400 if errors else 200)


@expenses_bp.route('/expenses/add', methods=['GET', 'POST'])
def add():
    return expense_form()


@expenses_bp.route('/expenses/<int:expense_id>/edit', methods=['GET', 'POST'])
def edit(expense_id):
    return expense_form(owned_expense(expense_id))


@expenses_bp.route('/expenses/<int:expense_id>/delete', methods=['GET', 'POST'])
def delete(expense_id):
    expense = owned_expense(expense_id)
    if request.method == 'POST':
        db = get_db()
        db.execute('DELETE FROM expenses WHERE id=? AND owner_token=?', (expense_id, session['expense_owner']))
        db.commit()
        flash('Expense deleted.')
        return redirect(url_for('expenses.index'), code=303)
    return render_template('expense_delete.html', expense=expense)
