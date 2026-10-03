"""Optional real-browser coverage of month selection and add-button state."""
from pathlib import Path
import os
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from src.app import app
from src.database.db import get_db


def main():
    fallback = os.environ.get('TEST_MONTH_FALLBACK') == '1'
    def label(month):
        return {'2026-10': 'October 2026', '2026-11': 'November 2026'}[month] if fallback else month

    with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
        app.config.update(TESTING=True, DATABASE=str(Path(directory) / 'browser.sqlite'),
                          SECRET_KEY='browser-test', REPORTING_RATE_PROVIDER=None)
        with app.app_context():
            db = get_db()
            db.execute("INSERT INTO users (name,email,password_hash,owner_token) VALUES ('Test','test@example.com','unused','browser')")
            db.execute('INSERT INTO account_preferences (user_id,income_enabled) VALUES (1,1)')
            db.commit()
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 1
            session['expense_owner'] = 'browser'

        def route(r):
            u = urlsplit(r.request.url)
            if u.netloc != 'spendwise.test':
                return r.abort()
            response = client.open(u.path + ('?' + u.query if u.query else ''), method=r.request.method,
                                   data=r.request.post_data, content_type=r.request.headers.get('content-type'))
            body = response.data
            if fallback and response.mimetype == 'text/html':
                # Simulate a browser that falls back from type=month to type=text.
                body = body.replace(b'type="month"', b'type="text"')
            r.fulfill(status=response.status_code, headers=dict(response.headers), body=body)

        chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        browser = p.chromium.launch(headless=True, **({'executable_path': str(chrome)} if chrome.exists() else {}))
        page = browser.new_page()
        page.route('**/*', route)
        for origin in ['overview', 'expenses', 'income', 'investments']:
            for month in ['2026-10', '2026-11']:
                for kind, field in [('expenses', 'expense_date'), ('income', 'income_date'), ('investments', 'investment_date')]:
                    page.goto('http://spendwise.test/' + origin + '?currency=USD&month=2026-10')
                    expect(page.locator('#filter-month')).to_have_value(label('2026-10'))
                    page.locator('#filter-month').fill(label(month))
                    page.get_by_role('button', name='Apply', exact=True).click()
                    assert parse_qs(urlsplit(page.url).query)['month'] == [month]
                    expect(page.locator('.income-actions .secondary-button')).to_have_count(3)
                    page.locator('.income-actions a[href^="/' + kind + '/add"]').click()
                    assert parse_qs(urlsplit(page.url).query)['month'] == [month]
                    expect(page.locator('input[name="month"]')).to_have_value(month)
                    expect(page.locator('#' + field)).to_have_value(month + '-01')
                    expect(page.locator('#currency')).to_have_value('USD')
                    expect(page.locator('.income-actions a[aria-current="page"]')).to_have_count(1)
                    expect(page.locator('.income-actions .secondary-button')).to_have_count(2)
                    page.get_by_role('link', name='Cancel', exact=True).click()
                    expect(page.locator('#filter-month')).to_have_value(label(month))
                    page.get_by_role('link', name='Overview', exact=True).click()
                    expect(page.locator('#filter-month')).to_have_value(label(month))
                    assert parse_qs(urlsplit(page.url).query)['month'] == [month]
        if fallback:
            page.locator('#filter-month').fill('October')
            assert not page.locator('#filter-month').evaluate('(input) => input.checkValidity()')
            page.locator('#filter-month').fill('')
            page.get_by_role('button', name='Apply', exact=True).click()
            expect(page.locator('input[name="month"]')).to_have_value('')
        browser.close()
        print('Passed 24 browser flows: month changes, add links, currency, active buttons, and cancel navigation.')


if __name__ == '__main__':
    main()
