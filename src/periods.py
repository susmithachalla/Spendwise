"""Canonical workspace period values, separate from presentation labels."""
from datetime import date
import re

from flask import abort, flash, g, redirect, request, session, url_for
from src.currencies import CURRENCIES


def parse_month(value):
    """An empty value means all dates; otherwise require a real YYYY-MM."""
    if value == '':
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}', value):
        raise ValueError('Choose a valid month.')
    date.fromisoformat(value + '-01')
    return value


def prepare_period():
    if request.blueprint not in ('expenses', 'income', 'investments'):
        return None
    stored = session.get('workspace_filters', {})
    try:
        fallback = parse_month(stored.get('month', ''))
    except ValueError:
        fallback = ''
    raw = request.form.get('month', request.args.get('month', fallback))
    try:
        month = parse_month(raw)
    except ValueError:
        flash('Choose a valid month. Your previous period has been restored.')
        filters = dict(stored, month=fallback)
        session['workspace_filters'] = filters
        # Never replay a failed POST or retain an invalid query value.
        endpoint = request.endpoint if request.method == 'GET' else 'expenses.overview'
        args = request.args.to_dict() if request.method == 'GET' else {}
        if request.method == 'GET':
            args.update(request.view_args or {})
        args['month'] = fallback
        return redirect(url_for(endpoint, **args), code=303)
    currency = request.args.get('currency', stored.get('currency', ''))
    if currency and currency not in CURRENCIES:
        if request.endpoint in ('expenses.index', 'expenses.overview', 'income.index', 'investments.index'):
            currency = ''  # Legacy dashboard currency filters never restrict reporting.
        else:
            abort(400, description='Choose a supported currency.')
    filters = {'currency': currency} if currency else {}
    filters['month'] = month
    session['workspace_filters'] = filters
    g.period_filters = {'currency': currency, 'month': month}


def period_args():
    return dict(g.period_filters)


def period_context():
    filters = session.get('workspace_filters', {})
    try:
        month = parse_month(filters.get('month', ''))
    except ValueError:
        month = ''
    canonical = {key: value for key, value in dict(filters, month=month).items() if value}
    return {'workspace_filters': canonical,
            'month_label': date.fromisoformat(month + '-01').strftime('%B %Y') if month else ''}
