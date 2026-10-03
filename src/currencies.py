"""Currency metadata and exact money handling; no exchange-rate conversion."""
from datetime import date
from decimal import Decimal
import re

from babel.core import Locale, get_global
from babel.numbers import (
    format_currency, get_currency_name, get_currency_precision,
    get_currency_symbol, get_territory_currencies,
)


def currency_options():
    # Reuse the same territory data for country-name search in the selector.
    territories = Locale.parse('en').territories
    countries = {}
    for territory in get_global('territory_currencies'):
        for code in get_territory_currencies(territory, start_date=date.today()):
            countries.setdefault(code, []).append(f'{territory} {territories.get(territory, territory)}')
    codes = set(countries)
    preferred = ['INR', 'USD', 'EUR', 'CAD']
    ordered = preferred + sorted(codes - set(preferred))
    return {
        code: {
            'name': get_currency_name(code, locale='en'),
            'symbol': get_currency_symbol(code, locale='en_IN' if code == 'INR' else 'en_US'),
            'digits': get_currency_precision(code),
            'countries': ' '.join(countries.get(code, [])),
        }
        for code in ordered
    }


CURRENCIES = currency_options()
# Bound individual entries well within SQLite's signed 64-bit integer range.
MAX_MINOR = 999_999_999_999_999


def parse_amount(raw, currency, *, allow_zero=False):
    if currency not in CURRENCIES:
        raise ValueError('Choose a supported currency from the list.')
    raw = raw.strip()
    if len(raw) > 24 or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', raw):
        raise ValueError('Enter a positive amount using a decimal point, without symbols or commas.')
    amount = Decimal(raw)
    digits = CURRENCIES[currency]['digits']
    scaled = amount * (10 ** digits)
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError('The amount must be greater than zero.')
    if scaled != scaled.to_integral_value():
        raise ValueError(f'{currency} supports {digits} decimal places. Please correct the amount; it has not been rounded.')
    if scaled > MAX_MINOR:
        raise ValueError('This amount is too large. Please enter a smaller amount.')
    return int(scaled), digits


def decimal_amount(minor, digits):
    return Decimal(minor).scaleb(-digits)


def money(minor, currency, digits):
    # Always show the code as well as a symbol, so USD and CAD are unambiguous.
    grouping = '#,##,##0' if currency == 'INR' else '#,##0'
    pattern = '¤ ' + grouping + ('.' + '0' * digits if digits else '')
    value = format_currency(decimal_amount(minor, digits), currency, format=pattern,
                            currency_digits=False, locale='en_IN' if currency == 'INR' else 'en_US')
    return f'{currency} {value}'
