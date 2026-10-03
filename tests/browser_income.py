"""Optional Playwright checks using an isolated database and Flask test client."""
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from src.app import app
from src.database.db import get_db


def main():
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
        app.config.update(TESTING=True, DATABASE=str(Path(directory) / 'browser.sqlite'), SECRET_KEY='browser-test')
        with app.app_context():
            db = get_db()
            db.execute("INSERT INTO users (name,email,password_hash,owner_token) VALUES ('Test','test@example.com','unused','browser')")
            db.execute("INSERT INTO expenses (owner_token,expense_date,description,category,amount_minor,currency,fraction_digits) VALUES ('browser','2026-10-01','Lunch','Groceries',2500,'USD',2)")
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
            r.fulfill(status=response.status_code, headers=dict(response.headers), body=response.data)
        chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        browser = p.chromium.launch(headless=True, **({'executable_path': str(chrome)} if chrome.exists() else {}))
        page = browser.new_page(viewport={'width': 1280, 'height': 900})
        page.route('**/*', route)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://spendwise.test/expenses?currency=USD&month=2026-10')
        nav = page.locator('.navbar')
        expect(nav.get_by_role('link', name='Income', exact=True)).to_have_count(0)
        nav.get_by_role('link', name='Overview', exact=True).click()
        page.locator('.income-preferences summary').click()
        page.get_by_role('button', name='Enable income tracking', exact=True).click()
        expect(page.locator('h1')).to_have_text('Add your first income')
        expect(page.locator('#income-category')).to_have_value('')
        page.get_by_role('link', name='Skip for now').click()
        expect(page.locator('h1')).to_have_text('Overview')
        expect(page.locator('.income-empty')).to_contain_text('No income added yet')
        expect(page.locator('.summary-card strong')).to_have_text(['—', 'USD $ 25.00', 'USD $ 0.00', '—'])
        page.get_by_role('link', name='Add income', exact=True).click()
        page.locator('#amount').fill('100')
        page.locator('#income-category').select_option('Salary')
        page.get_by_role('button', name='Save income', exact=True).click()
        expect(page.locator('h1')).to_have_text('Your income')
        expect(page.locator('[aria-label="Saved expenses"]')).to_have_count(0)
        page.locator('[aria-label="Saved income"]').get_by_role('link', name='Edit', exact=True).click()
        page.locator('#source').fill('Acme employer')
        page.locator('#notes').fill('October salary')
        page.get_by_role('button', name='Save changes').click()
        for width in (1440, 768, 375):
            page.set_viewport_size({'width': width, 'height': 900})
            for name, heading in [('Overview', 'Overview'), ('Expenses', 'Your expenses'), ('Income', 'Your income')]:
                nav.get_by_role('link', name=name, exact=True).click()
                expect(page.locator('h1')).to_have_text(heading)
                expect(page.locator('#filter-currency')).to_have_count(0)
                expect(page.locator('#filter-month')).to_have_value('2026-10')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                if name == 'Overview':
                    expect(page.locator('.summary-card strong')).to_have_text(['USD $ 100.00', 'USD $ 25.00', 'USD $ 0.00', 'USD $ 75.00'])
                else:
                    expect(page.locator('.monthly-trend').first).to_be_visible()
                    expect(page.locator('.doughnut').first).to_be_visible()
                page.screenshot(path=f'/tmp/spendwise-{name.lower()}-page-{width}.png', full_page=True)
            page.get_by_role('link', name='+ Add income', exact=True).click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.get_by_role('link', name='Cancel', exact=True).click()
            expect(page.locator('h1')).to_have_text('Your income')
        nav.get_by_role('link', name='Overview', exact=True).click()
        page.locator('.income-preferences summary').click()
        page.get_by_role('button', name='Disable income tracking', exact=True).click()
        expect(nav.get_by_role('link', name='Income', exact=True)).to_have_count(0)
        page.locator('.income-preferences summary').click()
        page.get_by_role('button', name='Enable income tracking', exact=True).click()
        page.locator('#amount').fill('50')
        page.locator('#income-category').select_option('Freelance')
        page.locator('#source').fill('Client')
        page.locator('#notes').fill('Project payment')
        page.get_by_role('button', name='Save income', exact=True).click()
        expect(page.locator('[aria-label="Saved income"] tbody tr')).to_have_count(2)
        with app.app_context():
            db = get_db()
            for category, amount in [('Dining & Drinks', 4500), ('Transportation', 1700), ('Housing', 90000)]:
                db.execute("INSERT INTO expenses (owner_token,expense_date,description,category,amount_minor,currency,fraction_digits) VALUES ('browser','2026-10-05',?,?,?, 'USD',2)", (category, category, amount))
            db.commit()
        for width in (1440, 768, 375):
            page.set_viewport_size({'width': width, 'height': 1000})
            for kind, single in [('expenses', 'category=Groceries'), ('income', 'income_category=Salary')]:
                for state, query in [('multi', 'month=2026-10'), ('single', 'month=2026-10&' + single), ('empty', 'month=2020-01')]:
                    page.goto('http://spendwise.test/' + kind + '?currency=USD&' + query)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    heights = page.locator('.expense-filters select, .expense-filters input, .expense-filters button').evaluate_all('(els) => els.map(e => e.getBoundingClientRect().height)')
                    assert all(abs(h - 44) < 1 for h in heights), heights
                    expect(page.locator('.expense-list')).to_have_count(1)
                    if state != 'empty':
                        ring = page.locator('.doughnut').first.bounding_box()
                        assert 239 <= ring['width'] <= 280
                        trend = page.locator('.trend-card').first.bounding_box()
                        category = page.locator('.breakdown-card').first.bounding_box()
                        assert (abs(trend['y'] - category['y']) < 1) if width == 1440 else category['y'] >= trend['y'] + trend['height']
                        target = page.locator('.doughnut-segment').first
                        target.focus()
                        expect(page.locator('.chart-tooltip')).to_be_visible()
                        page.keyboard.press('Escape')
                    page.screenshot(path=f'/tmp/spendwise-{kind}-{state}-{width}.png', full_page=True)
        page.goto('http://spendwise.test/overview?currency=USD&month=2026-10')
        page.get_by_role('link', name='+ Add investment', exact=True).click()
        page.locator('#amount').fill('50.25')
        page.locator('#investment-category').select_option('ETFs')
        page.locator('#notes').fill('ABC incl. purchase fees')
        page.get_by_role('button', name='Save investment', exact=True).click()
        expect(page.locator('.summary-card strong')).to_have_text(['USD $ 150.00', 'USD $ 987.00', 'USD $ 50.25', 'USD -$ 887.25'])
        for width in (1440, 768, 375):
            page.set_viewport_size({'width': width, 'height': 1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=f'/tmp/spendwise-investments-{width}.png', full_page=True)
        assert not errors, errors
        browser.close()
        print('Passed: three-page navigation, remembered filters, enable/skip/save/edit, conditional Income link, desktop/mobile layouts.')


if __name__ == '__main__':
    main()
