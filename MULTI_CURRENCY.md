# Spend Wise reporting currencies

Original expenses, income, and investment purchases always retain their entered currency and amount. The transaction lists display these originals.

## Currency detection

Dashboard reporting examines the current workspace's expenses and the signed-in account's investments and enabled income records **in the selected month** (or all dates when no month is selected), before category filtering. Hidden income is excluded while income tracking is off. Other users' records are never included.

- No transactions: empty dashboard; no exchange-rate requests.
- One currency: totals and charts remain in that currency; no conversion or rate requests.
- Two or more currencies: all reporting data is normalized to USD, with one four-card summary and one pair of charts. Old currency query parameters do not restrict dashboard data. Currency filters are removed; month is remembered across pages.

Summary cards cover all categories. The active category filter affects only charts and the transaction list. Remaining cash is recorded income minus expenses minus investments, not total wealth. Missing income produces a dash; an actual zero income entry produces a numeric zero.

## Rates and persistence

`reporting.py` is the single normalization layer. It uses [Frankfurter's public API](https://frankfurter.dev/) for USD-base rates on each transaction date. INR amounts are divided by INR-per-USD; the same convention applies to every quote currency. No amounts, notes, account IDs, or payer details are sent to the provider.

Rate precedence: cached rate, configured historical rate, public historical rate, configured current fallback, public latest fallback. The returned observation date and source are retained. Dates with no historical observation may use the latest fallback; future-dated entries also use a fallback.

`reporting_rates` caches date/currency rates. `reporting_conversions` retains the original currency/minor amount/precision, transaction date, rate, rate date/source, and resulting USD cents for each original transaction version. Edits to date, currency, or amount create a new conversion version; old audit values are preserved. Every conversion starts from the original amount, never from a previous reporting value. Single-currency mode ignores conversion snapshots and shows originals.

Each transaction is rounded once to USD cents using Decimal ROUND_HALF_UP; those same cents drive cards, category/monthly charts, and optional secondary transaction values. This makes all displayed transaction values sum to the reporting totals. USD transactions keep their original value.

A required missing/invalid rate makes all analytics unavailable for that report rather than silently omitting a currency. Original records remain available and editable. Retry after connectivity is restored or configure fallback rates. Cached conversions remain usable offline.

## Configuration

No invented rates ship with the app. To supply fallback rates, set `SPENDWISE_USD_RATES` to a JSON object of quote-currency units per USD before starting Flask. The application also accepts `REPORTING_HISTORICAL_RATES` as a date-to-currency-to-rate mapping in Flask configuration. `REPORTING_RATE_PROVIDER=None` disables network lookup for manual configuration or deterministic tests.

## Verification

Run `.venv/bin/python -m pytest -q`. Tests use explicitly labelled fixture rates without external network requests. The optional Playwright browser scripts use temporary databases; no user records are changed.


Investment activity uses a dedicated Investments history and activity subtype.
Contribution is cash invested; Return, Withdrawal, Dividend, Interest, Capital gain,
and Other income are cash received. All amounts remain positive in storage.
The shared reporting classifier counts cash received toward Income, contributions
only toward Investments, and ordinary expenses toward Expenses. Remaining cash is
Income minus Expenses minus Investments. Investment charts show gross activity by
subtype, while Income charts include investment cash received. Category/activity
filters do not change period summary totals or the period reporting currency.

Existing investment purchases default to Contribution through an idempotent schema
upgrade. Legacy Income records categorized as Investments appear as Return in
Investments history, with their original storage, amounts, currency, and edit/delete
identity preserved. These returns remain reportable when regular income tracking
is off. New investment income is entered through the Investments form.

## Source layout and navigation periods

Application Python modules, templates, and static assets live under `src/`.
Run `.venv/bin/python app.py` (compatibility launcher), or
`.venv/bin/python -m flask --app src.app run --port 5001` from the project root.
The existing root `instance/` database and session key remain in place.
Tests stay in `tests/` and import the `src` package.

`src/periods.py` validates navigation months as real `YYYY-MM` values. Empty
means all dates; omitted values retain the selected workspace period. Invalid
values redirect with a flash notice to the previous valid period. Templates use
`month_label` for readable headings and canonical workspace filters for links.
Currency is preserved for entry forms without restricting dashboard reporting.
Add-button active styling depends only on the exact add endpoint.
