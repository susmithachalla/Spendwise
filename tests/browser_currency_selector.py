"""Optional browser checks: .venv/bin/python tests/browser_currency_selector.py.

Requires Playwright plus Chrome (or Playwright's Chromium). Uses a temporary
database and routes browser requests through Flask's test client; no server needed.
"""
from pathlib import Path
import os
import sys
import tempfile
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright, expect
from src.app import app
from src.currencies import CURRENCIES


def main():
    chrome = os.environ.get('CHROME_EXECUTABLE', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    with tempfile.TemporaryDirectory() as directory, sync_playwright() as playwright:
        app.config.update(TESTING=True, DATABASE=str(Path(directory) / 'test.sqlite'), SECRET_KEY='browser-test-key')
        client = app.test_client()

        def route_request(route):
            request = route.request
            url = urlsplit(request.url)
            if url.netloc != 'spendwise.test':
                return route.abort()
            response = client.open(url.path + ('?' + url.query if url.query else ''),
                                   method=request.method, data=request.post_data,
                                   content_type=request.headers.get('content-type'))
            route.fulfill(status=response.status_code, headers=dict(response.headers), body=response.data)

        browser = playwright.chromium.launch(headless=True, **({'executable_path': chrome} if Path(chrome).exists() else {}))
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        context.route('**/*', route_request)
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://spendwise.test/expenses/add')
        trigger, search, popup = page.locator('#currency-trigger'), page.locator('#currency-search'), page.locator('#currency-popup')
        expect(trigger).to_contain_text('INR — Indian Rupee (₹)')
        expect(page.locator('#currency')).to_be_hidden()
        trigger.click()
        expect(search).to_be_focused()
        expect(trigger).to_have_attribute('aria-expanded', 'true')
        popular = page.get_by_role('group', name='Popular currencies')
        assert popular.locator('[role=option]').evaluate_all('(nodes) => nodes.map(n => n.dataset.code)') == ['INR','USD','EUR','GBP','CAD','AUD','AED','SGD']
        assert page.get_by_role('group', name='All currencies', exact=True).get_by_role('option').count() == len(CURRENCIES)
        assert popup.bounding_box()['height'] <= 321
        assert page.locator('#currency-results').evaluate('(el) => el.scrollHeight > el.clientHeight')

        for query, code in [('Canada', 'CAD'), ('Germany', 'EUR'), ('cad', 'CAD'), ('₹', 'INR'), ('pound', 'GBP')]:
            search.fill(query)
            expect(page.locator(f'[role=option][data-code="{code}"]')).to_be_visible()
        search.fill('no-such-currency')
        expect(page.locator('.currency-empty')).to_be_visible()
        expect(search).not_to_have_attribute('aria-activedescendant')
        search.press('Enter')
        assert urlsplit(page.url).path == '/expenses/add'
        assert page.locator('#currency').input_value() == 'INR'
        search.press('Escape')
        expect(popup).to_be_hidden()
        expect(trigger).to_be_focused()

        trigger.press('ArrowDown')
        search.fill('CAD')
        search.press('Enter')
        expect(popup).to_be_hidden()
        assert page.locator('#currency').input_value() == 'CAD'
        expect(page.locator('#amount-code')).to_have_text('(CAD)')
        assert page.locator('form.expense-form').evaluate('(form) => new FormData(form).getAll("currency")') == ['CAD']

        trigger.click()
        search.press('ArrowDown')
        search.press('Escape')
        assert page.locator('#currency').input_value() == 'CAD'
        trigger.click()
        search.press('Tab')
        expect(page.locator('#amount')).to_be_focused()
        expect(popup).to_be_hidden()
        trigger.click()
        page.locator('h1').click()
        expect(popup).to_be_hidden()

        trigger.click()
        search.fill('JPY')
        page.locator('[role=option][data-code=JPY]').click()
        expect(page.locator('#amount-help')).to_contain_text('whole amounts only')
        page.locator('#amount').fill('125')
        page.locator('#description').fill('Browser selector test')
        page.get_by_role('button', name='Save expense', exact=True).click()
        page.wait_for_url('**/expenses')
        expect(page.locator('table')).to_contain_text('JPY ¥ 125')
        page.get_by_role('link', name='Edit Browser selector test').click()
        expect(page.locator('#currency-trigger')).to_contain_text('JPY')
        assert page.locator('#currency').input_value() == 'JPY'

        # 375px mobile layout, independently scrollable list, and keyboard scrolling.
        page.set_viewport_size({'width': 375, 'height': 740})
        page.locator('#currency-trigger').click()
        search.fill('dollar')
        assert popup.bounding_box()['height'] <= 321
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        box = popup.bounding_box()
        assert box['x'] >= 0 and box['x'] + box['width'] <= 375
        search.fill('')
        for _ in range(20):
            search.press('ArrowDown')
        assert page.locator('#currency-results').evaluate('(el) => el.scrollTop > 0')
        active_id = search.get_attribute('aria-activedescendant')
        expect(page.locator('#' + active_id)).to_have_attribute('aria-selected', 'true')
        screenshot = os.environ.get('CURRENCY_SCREENSHOT')
        if screenshot:
            search.fill('dollar')
            page.screenshot(path=screenshot, full_page=True)
        assert not errors, errors

        fallback = browser.new_context(java_script_enabled=False)
        fallback.route('**/*', route_request)
        fallback_page = fallback.new_page()
        fallback_page.goto('http://spendwise.test/expenses/add')
        expect(fallback_page.locator('#currency')).to_be_visible()
        assert fallback_page.locator('#currency option').count() == len(CURRENCIES)
        fallback.close()
        browser.close()
        print('Browser checks passed: source data, popular group, country/name/code/symbol search, keyboard/focus, empty state, exact submission, edit, mobile scrolling, and no-JS fallback.')


if __name__ == '__main__':
    main()
