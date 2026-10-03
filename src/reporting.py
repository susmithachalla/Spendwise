"""Reporting-only normalization. Stored transaction amounts are never modified."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError

from flask import current_app
from src.currencies import decimal_amount, money
from src.database.db import get_db


class RateUnavailable(ValueError):
    pass


def positive_rate(value):
    try:
        rate = Decimal(str(value))
        if not rate.is_finite() or rate <= 0:
            raise ValueError
        return rate
    except (InvalidOperation, ValueError, TypeError):
        raise RateUnavailable('Invalid exchange rate.') from None


def public_rate(currency, requested_date):
    params = {'date': requested_date} if requested_date else {}
    url = 'https://api.frankfurter.dev/v2/rate/usd/' + currency.lower() + '?' + urlencode(params)
    with urlopen(Request(url, headers={'User-Agent': 'SpendWise/1.0', 'Accept': 'application/json'}), timeout=3) as response:
        data = json.loads(response.read(65536), parse_float=Decimal)
    if data.get('base', '').upper() != 'USD' or data.get('quote', '').upper() != currency:
        raise RateUnavailable('Unexpected currency pair.')
    rate_date = date.fromisoformat(data['date']).isoformat()
    if requested_date and rate_date > requested_date:
        raise RateUnavailable('Historical rate is after the transaction date.')
    return positive_rate(data['rate']), rate_date, 'Frankfurter historical' if requested_date else 'Frankfurter latest fallback'


def resolve_rate(currency, transaction_date):
    if currency == 'USD':
        return Decimal(1), transaction_date, 'USD identity'
    db = get_db()
    cached = db.execute('SELECT * FROM reporting_rates WHERE currency=? AND requested_date=?',
                        (currency, transaction_date)).fetchone()
    if cached:
        return positive_rate(cached['units_per_usd']), cached['rate_date'], cached['source']
    historical = current_app.config.get('REPORTING_HISTORICAL_RATES', {}).get(transaction_date, {}).get(currency)
    result = None
    if historical is not None:
        result = positive_rate(historical), transaction_date, 'Configured historical'
    provider = current_app.config.get('REPORTING_RATE_PROVIDER', public_rate)
    if result is None and provider and transaction_date <= date.today().isoformat():
        try:
            result = provider(currency, transaction_date)
        except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
            pass
    if result is None:
        configured = current_app.config.get('REPORTING_CURRENT_RATES', {}).get(currency)
        if configured is not None:
            result = positive_rate(configured), date.today().isoformat(), 'Configured current fallback'
    if result is None and provider:
        try:
            result = provider(currency, None)
        except (URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
            pass
    if result is None:
        raise RateUnavailable(f'Exchange rate unavailable for {currency} on {transaction_date}. Totals are unavailable until a rate can be loaded or configured.')
    rate, rate_date, source = result
    rate = positive_rate(rate)
    with db:
        db.execute('INSERT OR IGNORE INTO reporting_rates VALUES (?,?,?,?,?)',
                   (currency, transaction_date, str(rate), rate_date, source))
    return rate, rate_date, source


def normalize(row, kind):
    """Return a new USD reporting row, keeping a conversion audit per original version."""
    original = dict(row)
    stamp = [kind, original['id'], original.get('owner_token', original.get('user_id')),
             original.get('created_at'), original['expense_date'], original['currency'],
             original['amount_minor'], original['fraction_digits']]
    fingerprint = hashlib.sha256(json.dumps(stamp).encode()).hexdigest()
    db = get_db()
    audit = db.execute('SELECT * FROM reporting_conversions WHERE fingerprint=?', (fingerprint,)).fetchone()
    if audit is None:
        rate, rate_date, source = resolve_rate(original['currency'], original['expense_date'])
        with localcontext() as ctx:
            ctx.prec = 50
            usd_minor = int((decimal_amount(original['amount_minor'], original['fraction_digits']) / rate * 100)
                            .quantize(Decimal(1), rounding=ROUND_HALF_UP))
        with db:
            db.execute('''INSERT OR IGNORE INTO reporting_conversions
                (fingerprint, kind, transaction_id, original_currency, original_minor, original_digits,
                 transaction_date, units_per_usd, rate_date, source, usd_minor)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (fingerprint, kind, original['id'], original['currency'], str(original['amount_minor']),
                 original['fraction_digits'], original['expense_date'], str(rate), rate_date, source, str(usd_minor)))
        audit = db.execute('SELECT * FROM reporting_conversions WHERE fingerprint=?', (fingerprint,)).fetchone()
    original.update(currency='USD', fraction_digits=2, amount_minor=int(audit['usd_minor']))
    return original, dict(audit)


INVESTMENT_SUBTYPES = ('Contribution', 'Return', 'Withdrawal', 'Dividend', 'Interest', 'Capital gain', 'Other income')


def classify_datasets(datasets):
    """Classify original rows once; storage identity stays available for edits/audits."""
    result = {kind: [] for kind in ('expenses', 'income', 'investments')}
    for kind, rows in datasets.items():
        for row in rows:
            item = dict(row, storage_kind=kind)
            target = kind
            if kind == 'income' and item['category'] == 'Investments':
                target = 'investments'
                item.update(subtype='Return', investment_type='Other', investment_date=item['income_date'])
                item['notes'] = ' · '.join(filter(None, (item.get('source'), item.get('notes'))))
            if target == 'investments':
                item['category'] = item.get('subtype', 'Contribution')
                item['cash_role'] = 'investments' if item['category'] == 'Contribution' else 'income'
            else:
                item['cash_role'] = target
            result[target].append(item)
    result['investments'].sort(key=lambda r: (r['expense_date'], r['id']), reverse=True)
    return result


def cash_datasets(datasets):
    result = {kind: [] for kind in ('expenses', 'income', 'investments')}
    for rows in datasets.values():
        for row in rows:
            result[row['cash_role']].append(row)
    return result


def build_report(datasets):
    currencies = sorted({row['currency'] for rows in datasets.values() for row in rows})
    multi = len(currencies) > 1
    code = 'USD' if multi else currencies[0] if currencies else None
    result = dict(isMultiCurrency=multi, reportingCurrency=code, datasets={}, conversions={}, error=None)
    try:
        for kind, rows in datasets.items():
            result['datasets'][kind] = []
            for row in rows:
                if multi:
                    normalized, audit = normalize(row, row.get('storage_kind', kind))
                    result['conversions'][(row.get('storage_kind', kind), row['id'])] = audit
                else:
                    normalized = dict(row)
                result['datasets'][kind].append(normalized)
    except RateUnavailable as error:
        result['error'] = str(error)
        result['datasets'] = {kind: [] for kind in datasets}  # Never show misleading partial totals.
    return result


def report_balances(report, has_income):
    code = report['reportingCurrency']
    if not code:
        return []
    if report['error']:
        return [dict(currency=code, income='—', expenses='—', investments='—', remaining='—', has_income=False)]
    rows = [r for group in report['datasets'].values() for r in group]
    digits = max(row['fraction_digits'] for row in rows)
    totals = {kind: sum((decimal_amount(r['amount_minor'], r['fraction_digits']) for r in group), Decimal(0))
              for kind, group in cash_datasets(report['datasets']).items()}
    def display(amount):
        return money(int(amount.scaleb(digits)), code, digits)
    return [dict(currency=code, income=display(totals['income']) if has_income else '-',
                 expenses=display(totals['expenses']), investments=display(totals['investments']),
                 remaining=display(totals['income']-totals['expenses']-totals['investments']) if has_income else '-',
                 has_income=has_income)]
