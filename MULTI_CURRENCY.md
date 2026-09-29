# Spend Wise: multi-currency expenses

## Run and try it

From `/Users/susmithachalla/Documents/expense-tracker`:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open http://localhost:5001/expenses or choose **Expenses** in the navigation. Add an amount, currency, description, date, and category. INR, USD, EUR, and CAD appear first, followed by other current tender currencies from Babel's bundled CLDR data. This is currency recording, not currency conversion; cryptocurrency and arbitrary custom codes are not included.

For example, add INR 500, USD 10, EUR 8, and CAD 12. You will see four separate totals. They must not become a single total of 530: the units differ. USD and CAD both use dollar symbols, so every display includes its currency code.

## What changed, where, and why

| File | Change | Why |
| --- | --- | --- |
| `currencies.py` | Currency names, symbols, supported codes, decimal rules, validation, and formatting. | One source of truth for currency behavior. INR/USD/EUR/CAD use two decimal places, JPY uses zero, and KWD uses three. Unsupported precision is rejected rather than silently rounded. |
| `database/db.py` | Adds SQLite storage with `amount_minor`, `currency`, and `fraction_digits` on each expense. | Amounts remain exact: INR 125.50 becomes integer 12550 with precision 2. The currency and precision stay with the record rather than depending on a global setting. |
| `expenses.py` | Adds list, add, edit, and delete routes; server validation; currency/month filtering; per-currency totals. | Implements the previously placeholder expense workflow end to end. Each query is scoped to the current browser workspace. POST forms require a security token and deletion requires confirmation. |
| `app.py` | Registers expense routes, closes database connections, and configures signed browser sessions. | Wires the feature into Flask and preserves workspace access across server restarts using a stable signing key. |
| `templates/expense_*.html`, `templates/expenses.html` | Form, list, empty state, totals, delete confirmation, and workspace notice. | Users can choose currencies and see exactly what was saved. Errors preserve form entries. Editing a currency does not convert the amount. |
| `static/css/expenses.css`, `static/js/expenses.js` | Navy/teal responsive styling and currency-specific amount guidance. | Matches Spend Wise and explains decimal rules. JavaScript only changes guidance; saving, validation, filtering, and deletion also work without it. |
| `templates/base.html`, `templates/landing.html`, `static/css/style.css` | Adds navigation and a landing-page entry point, including on mobile. | Makes the feature discoverable. Landing-page sample charts are still illustrative. |
| `templates/privacy.html` | Documents stored records, session cookies, deletion, and browser access. | The earlier policy stated expense storage did not exist; it must reflect the new behavior. |
| `requirements.txt`, `.gitignore` | Adds Babel and excludes local database, secrets, caches, and virtual environment. | Supplies maintained currency metadata and keeps local runtime files out of source control. |
| `tests/test_expenses.py` | Covers precision, distinct totals, validation, editing, deletion, persistence, escaping, and workspace isolation. | Verifies money handling and access boundaries, including invalid requests sent directly to the server. |

Currency metadata comes from [Babel's currency APIs](https://babel.pocoo.org/en/latest/api/numbers.html), not an exchange-rate service. Update the pinned dependency when currency definitions change.

## Searchable currency selector

The expense form now enhances the existing currency select with a compact searchable dropdown. Popular currencies (INR, USD, EUR, GBP, CAD, AUD, AED, SGD) appear first; all supported currencies remain available below. Search matches codes, currency names, symbols, and country names derived from the same Babel territory data. No second currency catalog is maintained.

The popup is capped at 320px, scrolls internally, and opens above the field when that offers more space. Arrow keys navigate, Enter chooses, Escape cancels, and Tab leaves the control. Search has combobox/listbox semantics, active-option announcements, and a no-results state. The native select remains the source of the submitted `currency` value and works as a fallback without JavaScript. Database storage, supported currency codes, decimal rules, and server validation are unchanged.

The component lives in `static/js/expenses.js` and `static/css/expenses.css`; `templates/expense_form.html` exposes the existing options and country-search metadata. No frontend framework is used.

## Storage and current limits

This project had no functioning account system or expense database. This feature creates a **browser workspace**, not a logged-in account. A signed HttpOnly cookie identifies it; different browser profiles have separate records. Anyone using the same browser profile can access its workspace. Records are stored in `instance/spendwise.sqlite`; the persistent signing key is in `instance/.secret_key` unless `SPENDWISE_SECRET_KEY` is set. Keep that key private and stable. The local server uses HTTP; use HTTPS and secure cookies if adapting it for deployment.

The cookie renews with use and expires after a year of inactivity. Clearing it loses workspace access, but does not remove database records. No account recovery or cross-device sync exists yet. Delete unwanted records using the expense list before clearing cookies. Database deletion does not purge independent backups.

No existing expense migration was needed because the original Spend Wise database module was empty. ExpenseFlow v2 and its database were not changed. Budgets, live charts, recurring rules, and account authentication are still unimplemented in Spend Wise; this change does not claim to implement them. Future budgets and recurring rules must also store a currency, and charts must filter or group by currency. Automatic conversion would additionally require a chosen base currency, dated exchange rates, a rate source, and an explicit conversion policy.

## Verification

```sh
.venv/bin/python -m pytest -q
```

Tests use temporary databases, not the user's expense records.

Optional browser checks (requires Playwright and Chrome, or Playwright's installed Chromium):

```sh
.venv/bin/python -m pip install playwright
.venv/bin/python tests/browser_currency_selector.py
```

These check country/name/code/symbol search, popular and full lists, keyboard/focus behavior, unchanged form submission, editing, mobile scrolling, and the no-JavaScript fallback. They use a temporary database and browser profile.
