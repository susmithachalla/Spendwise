"""Follow rendered navigation links, rather than constructing add URLs ourselves."""
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import pytest
from test_income import client, toggle
from src.periods import parse_month


class Elements(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.links, self.inputs = [], {}
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            self.links.append(attrs)
        if tag == 'input':
            self.inputs[attrs.get('name')] = attrs.get('value')

    def adds(self):
        return [a for a in self.links if urlsplit(a.get('href', '')).path in
                ('/expenses/add', '/income/add', '/investments/add') and 'expense-button' in a.get('class', '')]


@pytest.mark.parametrize('origin', ['/overview', '/expenses', '/income', '/investments'])
@pytest.mark.parametrize('month', ['2026-10', '2026-11'])
def test_rendered_add_navigation(client, origin, month):
    toggle(client)
    page = Elements(client.get(origin + '?currency=USD&month=' + month))
    assert len(page.adds()) == 3
    for link in page.adds():
        assert 'secondary-button' in link['class']
        assert 'aria-current' not in link
        assert parse_qs(urlsplit(link['href']).query) == {'currency': ['USD'], 'month': [month]}
        response = client.get(link['href'])
        assert response.status_code == 200
        form = Elements(response)
        assert form.inputs['month'] == month
        kind = urlsplit(link['href']).path.split('/')[1]
        field = {'expenses': 'expense_date', 'income': 'income_date', 'investments': 'investment_date'}[kind]
        assert form.inputs[field] == month + '-01'
        assert '<option value="USD"' in response.text
        # Each form carries the selected period when switching to another add page.
        for action in form.adds():
            active = urlsplit(action['href']).path == '/' + kind + '/add'
            assert ('secondary-button' not in action['class']) == active
            assert (action.get('aria-current') == 'page') == active
            assert parse_qs(urlsplit(action['href']).query)['month'] == [month]
        back = next(a for a in form.links if a.get('class') == 'expense-link')
        assert parse_qs(urlsplit(back['href']).query) == {'currency': ['USD'], 'month': [month]}
        returned = client.get(back['href'])
        assert returned.status_code == 200
        assert Elements(returned).inputs['month'] == month


@pytest.mark.parametrize('bad', ['October', '2026-13', '2026-00', '2026-1', '0000-01', '202610', '2026-02-01'])
def test_invalid_month_recovers_previous_period(client, bad):
    toggle(client)
    client.get('/overview?currency=USD&month=2026-10')
    for path in ['/overview', '/expenses', '/income', '/investments', '/expenses/add', '/income/add', '/investments/add']:
        response = client.get(path + '?month=' + bad)
        assert response.status_code == 303
        assert parse_qs(urlsplit(response.location).query)['month'] == ['2026-10']
        restored = client.get(response.location)
        assert restored.status_code == 200
        assert 'Your previous period has been restored.' in restored.text


def test_defaults_clear_and_display_label(client):
    toggle(client)
    page = client.get('/expenses?month=2026-10&currency=USD')
    assert 'October 2026' in page.text
    assert Elements(client.get('/income/add')).inputs['income_date'] == '2026-10-01'
    client.get('/overview?month=&currency=')
    with client.session_transaction() as session:
        assert session['workspace_filters'] == {'month': ''}
    with pytest.raises(ValueError):
        parse_month('October')
    assert parse_month('2024-02') == '2024-02'


def test_posted_month_and_expense_return(client):
    toggle(client)
    form = Elements(client.get('/expenses/add?currency=USD&month=2026-10'))
    response = client.post('/expenses/add?currency=USD', data={
        'csrf_token': form.inputs['csrf_token'], 'month': '2026-10',
        'currency': 'USD', 'amount': '12', 'description': 'Lunch',
        'category': 'Groceries', 'expense_date': '2026-10-02'})
    assert response.status_code == 303
    assert parse_qs(urlsplit(response.location).query) == {'currency': ['USD'], 'month': ['2026-10']}
    response = client.post('/expenses/add', data={'month': 'October'})
    assert response.status_code == 303
    assert client.get(response.location).status_code == 200
