"""Visual reporting checks with deterministic fixture rates and a temporary database."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from src.app import app
from src.database.db import get_db

with TemporaryDirectory() as directory, sync_playwright() as p:
    app.config.update(TESTING=True, DATABASE=str(Path(directory)/'reporting.sqlite'), SECRET_KEY='test',
                      REPORTING_RATE_PROVIDER=None, REPORTING_CURRENT_RATES={'INR':'80'})
    with app.app_context():
        db=get_db()
        db.execute("INSERT INTO users (name,email,password_hash,owner_token) VALUES ('Test','test@example.com','unused','test')")
        db.execute('INSERT INTO account_preferences VALUES (1,1)')
        for month,code,amount in [('09','INR',800000),('10','USD',10000)]:
            db.execute("INSERT INTO expenses (owner_token,expense_date,description,category,amount_minor,currency,fraction_digits) VALUES ('test',?,'Purchase','Groceries',?,?,2)",('2026-'+month+'-02',amount,code))
            db.execute("INSERT INTO income (user_id,income_date,category,amount_minor,currency,fraction_digits) VALUES (1,?,'Salary',?,?,2)", ('2026-'+month+'-02',amount*2,code))
        db.commit()
    client=app.test_client()
    with client.session_transaction() as s:
        s['user_id']=1; s['expense_owner']='test'
    def route(r):
        u=urlsplit(r.request.url)
        if u.netloc!='spendwise.test': return r.abort()
        response=client.get(u.path+('?' + u.query if u.query else ''))
        r.fulfill(status=response.status_code, headers=dict(response.headers), body=response.data)
    browser=p.chromium.launch(headless=True, executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    page=browser.new_page(); page.route('**/*',route)
    errors=[]; page.on('pageerror', lambda e:errors.append(str(e)))
    for width in [1440,768,375]:
        page.set_viewport_size({'width':width,'height':1000})
        for mode,month,code,total in [('inr','2026-09','INR','INR ₹ 8,000.00'),('usd','2026-10','USD','USD $ 100.00'),('mixed','','USD','USD $ 200.00')]:
            page.goto('http://spendwise.test/expenses?month='+month)
            expect(page.locator('#filter-currency')).to_have_count(0)
            expect(page.locator('.summary-row')).to_have_count(1)
            expect(page.locator('.summary-card')).to_have_count(4)
            expect(page.locator('.chart-pair')).to_have_count(1)
            expect(page.locator('.summary-card strong').nth(1)).to_have_text(total)
            expect(page.locator('.doughnut-total strong')).to_have_text(total)
            assert ('Multiple currencies detected' in page.content()) == (mode=='mixed')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            if mode=='mixed':
                expect(page.locator('.expense-table')).to_contain_text('INR ₹ 8,000.00')
                expect(page.locator('.reporting-value')).to_have_count(1)
            page.screenshot(path=f'/tmp/spendwise-report-{mode}-{width}.png', full_page=True)
        page.locator('.transaction-switch').get_by_role('link', name='Income', exact=True).click()
        expect(page.locator('.doughnut-total strong')).to_have_text('USD $ 400.00')
        expect(page.locator('.expense-list')).to_have_count(1)
    assert not errors, errors
    browser.close()
    print('Passed INR-only, USD-only, mixed-USD summaries/charts, original amounts, filters, switching, and 3 viewport sizes.')
