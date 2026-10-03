"""Expense routes scoped to an account or anonymous browser workspace."""
from datetime import date
import secrets

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from src.charts import build_charts
from src.periods import period_args
from src.income import enabled, account, INCOME_CATEGORIES
from src.reporting import build_report, report_balances, classify_datasets, cash_datasets, INVESTMENT_SUBTYPES
from src.currencies import CURRENCIES, decimal_amount, money, parse_amount
from src.database.db import get_db
from src.categories import CATEGORIES, CATEGORY_GROUPS, LEGACY_MAPPINGS, LEGACY_DESCRIPTION, category_icon_path

expenses_bp = Blueprint('expenses', __name__)


@expenses_bp.app_context_processor
def category_icon_context():
    return {'category_icon_path': category_icon_path, 'nav_income_enabled': enabled()}


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
    return dashboard_page('expense')


@expenses_bp.get('/overview')
def overview():
    return dashboard_page('overview')


def dashboard_page(page):
    filters = period_args()
    month = filters['month']
    all_expenses = get_db().execute('SELECT * FROM expenses WHERE owner_token=? ORDER BY expense_date DESC, id DESC',
                                   (session['expense_owner'],)).fetchall()
    income_enabled = enabled()
    user = account()
    income_rows, investment_rows = [], []
    if user:
        investment_rows = get_db().execute('SELECT *, investment_date AS expense_date FROM investments WHERE user_id=? ORDER BY investment_date DESC, id DESC', (user['id'],)).fetchall()
        income_rows = get_db().execute('SELECT *, income_date AS expense_date FROM income WHERE user_id=? ORDER BY income_date DESC, id DESC', (user['id'],)).fetchall()
    def period(rows):
        return [row for row in rows if not month or row['expense_date'].startswith(month)]
    datasets = dict(expenses=period(all_expenses), income=period(income_rows), investments=period(investment_rows))
    datasets = classify_datasets(datasets)
    if not income_enabled:
        datasets['income'] = []
    report = build_report(datasets)
    cash_rows = cash_datasets(report['datasets'])
    has_income = bool(cash_datasets(datasets)['income'])
    subtype = request.args.get('subtype', '') if page == 'investments' else ''
    if subtype and subtype not in INVESTMENT_SUBTYPES:
        abort(400, description='Choose a valid investment activity.')
    investment_rows = [r for r in datasets['investments'] if not subtype or r['subtype'] == subtype]
    category = LEGACY_MAPPINGS.get(request.args.get('category', ''), request.args.get('category', '')) if page == 'expense' else ''
    legacy_categories = sorted({row['category'] for row in all_expenses} - CATEGORIES.keys())
    if category and category not in CATEGORIES and category not in legacy_categories:
        abort(400, description='Unknown category filter.')
    income_category = request.args.get('income_category', '') if page == 'income' else ''
    if income_category and income_category not in INCOME_CATEGORIES:
        abort(400, description='Choose a valid income category.')
    expenses = [row for row in datasets['expenses'] if not category or row['category'] == category]
    income_rows = [row for row in datasets['income'] if not income_category or row['category'] == income_category]
    normalized_expenses = [row for row in report['datasets']['expenses'] if not category or row['category'] == category]
    normalized_income = [row for row in cash_rows['income'] if not income_category or row['category'] == income_category or (income_category == 'Investments' and 'investment_type' in row)]
    summaries, charts = build_charts(normalized_income if page == 'income' else normalized_expenses,
                                    INCOME_CATEGORIES if page == 'income' else CATEGORIES)
    if page == 'investments':
        summaries, charts = build_charts([r for r in report['datasets']['investments'] if not subtype or r['subtype'] == subtype], {})
    period_summaries, _ = build_charts(report['datasets']['expenses'], CATEGORIES)
    _, income_charts = build_charts(normalized_income, INCOME_CATEGORIES)
    def attach_conversion(rows, kind):
        result = []
        for row in rows:
            item = dict(row)
            audit = report['conversions'].get((row.get('storage_kind', kind), row['id']))
            if audit and row['currency'] != 'USD' and report['isMultiCurrency'] and not report['error']:
                item['reporting_display'] = money(int(audit['usd_minor']), 'USD', 2)
                item['reporting_rate'] = audit['units_per_usd']
                item['reporting_rate_date'] = audit['rate_date']
            result.append(item)
        return result
    return render_template({'expense': 'expenses.html', 'income': 'income.html', 'overview': 'overview.html', 'investments': 'dashboard.html'}[page],
        expenses=attach_conversion(expenses, 'expenses'), income_rows=attach_conversion(income_rows, 'income'),
        investment_rows=attach_conversion(investment_rows, 'investments'), investment_subtypes=INVESTMENT_SUBTYPES, investment_subtype=subtype,
        income_enabled=income_enabled, has_period_income=has_income,
        income_categories=INCOME_CATEGORIES, income_category=income_category, income_charts=income_charts,
        income_currencies=sorted({r['currency'] for r in datasets['income']}),
        balances=report_balances(report, has_income),
        selected=report['reportingCurrency'] or '', available=[], month=month, charts=charts, summaries=summaries,
        category=category, chart_kind=page, category_groups=CATEGORY_GROUPS, legacy_categories=legacy_categories,
        period_summaries=period_summaries, reporting=report)


def expense_form(existing=None):
    filters = period_args()
    values = {'expense_date': filters['month'] + '-01' if filters['month'] else date.today().isoformat(), 'description': '', 'category': '',
              'currency': filters['currency'] or session.get('last_currency', 'INR'), 'amount': ''}
    if existing is not None:
        values.update(dict(existing))
        values['amount'] = str(decimal_amount(existing['amount_minor'], existing['fraction_digits']))
    legacy_category = existing['category'] if existing is not None and existing['category'] not in CATEGORIES else None
    errors = []
    if request.method == 'POST':
        values = {key: request.form.get(key, '').strip() for key in
                  ('expense_date', 'description', 'category', 'currency', 'amount')}
        if not 1 <= len(values['description']) <= 200:
            errors.append('Enter a description between 1 and 200 characters.')
        if values['category'] not in CATEGORIES and values['category'] != legacy_category:
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
            return redirect(url_for('expenses.index', **period_args()), code=303)
    return render_template('expense_form.html', values=values, errors=errors,
                           currencies=CURRENCIES, categories=CATEGORIES, category_groups=CATEGORY_GROUPS,
                           legacy_category=legacy_category, legacy_description=LEGACY_DESCRIPTION,
                           editing=existing is not None, filters=filters), (400 if errors else 200)


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
        return redirect(url_for('expenses.index', **period_args()), code=303)
    return render_template('expense_delete.html', expense=expense)
