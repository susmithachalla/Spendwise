"""Shared expense taxonomy, presentation, and unambiguous legacy mappings."""
CATEGORY_GROUPS = {
    'Food & drinks': (
        ('Groceries', 'Supermarket food and cooking ingredients', '#668d87'),
        ('Dining & Drinks', 'Restaurants, takeout, coffee, snacks', '#743b50'),
    ),
    'Home & essentials': (
        ('Housing', 'Rent, mortgage, home repairs', '#c29557'),
        ('Utilities & Internet', 'Electricity, water, gas, internet, phone', '#6b819a'),
        ('Transportation', 'Uber, public transit, fuel, parking', '#807299'),
        ('Health & Wellness', 'Medical visits, medicines, fitness', '#a65d42'),
    ),
    'Lifestyle': (
        ('Shopping & Personal Care', 'Clothing, electronics, toiletries, salon visits', '#bc7182'),
        ('Entertainment', 'Movies, games, events, hobbies', '#487878'),
        ('Subscriptions', 'Recurring streaming, software, memberships', '#9c8042'),
        ('Travel', 'Hotels, flights, vacation expenses', '#546a97'),
    ),
    'Learning & giving': (
        ('Education', 'Courses, books, tuition', '#92619a'),
        ('Gifts & Donations', 'Gifts and charitable contributions', '#ba7957'),
    ),
    'Other': (('Other', 'Expenses that don’t fit above', '#a99c78'),),
}
CATEGORIES = {name: {'description': description, 'color': color}
              for items in CATEGORY_GROUPS.values() for name, description, color in items}
LEGACY_MAPPINGS = {'Transport': 'Transportation', 'Health': 'Health & Wellness',
                   'Shopping': 'Shopping & Personal Care'}
LEGACY_DESCRIPTION = 'Existing category. Keep it unchanged or choose a more specific category.'

# All icons share a 24px viewBox and a 1.6px outline, like the landing icons.
CATEGORY_ICONS = {
    'Groceries': 'M3 9h18l-2 11H5L3 9Z M8 9l3-6m5 6-3-6M8 13v3m4-3v3m4-3v3',
    'Dining & Drinks': 'M4 3v5a3 3 0 0 0 6 0V3M7 3v18M20 3c-4 2-5 6-5 10h5m0-10v18',
    'Housing': 'm3 11 9-8 9 8M5 10v11h14V10M10 21v-7h4v7',
    'Utilities & Internet': 'M9 18h6m-5 3h4M9 15c0-2-4-3-4-7a7 7 0 0 1 14 0c0 4-4 5-4 7H9Z',
    'Transportation': 'm5 11 2-6a2 2 0 0 1 2-1h6a2 2 0 0 1 2 1l2 6M5 11h14a2 2 0 0 1 2 2v5H3v-5a2 2 0 0 1 2-2ZM5 18v3m14-3v3M6 14h2m8 0h2',
    'Health & Wellness': 'M9 3h6v6h6v6h-6v6H9v-6H3V9h6V3Z',
    'Shopping & Personal Care': 'M5 7h14l1 14H4L5 7ZM8 8V6a4 4 0 0 1 8 0v2',
    'Entertainment': 'M3 9h18v12H3V9Zm0 0-1-5 18-3 1 5-18 3Zm4-6 3 5m3-6 3 5M3 13h18',
    'Subscriptions': 'm17 2 4 4-4 4M21 6H7a4 4 0 0 0-4 4m4 12-4-4 4-4m-4 4h14a4 4 0 0 0 4-4',
    'Travel': 'M5 6h14a2 2 0 0 1 2 2v11H3V8a2 2 0 0 1 2-2ZM8 6V3h8v3M7 6v13m10-13v13M6 19v2m12-2v2',
    'Education': 'm2 9 10-5 10 5-10 5L2 9Zm4 2v6c4 3 8 3 12 0v-6m4-2v8',
    'Gifts & Donations': 'M3 8h18v5H3V8Zm2 5v8h14v-8M12 8v13m0-13H8a3 3 0 1 1 3-3l1 3Zm0 0h4a3 3 0 1 0-3-3l-1 3Z',
    'Other': 'M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z',
}


def category_icon_path(name):
    # Visual alias only: legacy Food remains ambiguous and is never migrated.
    if name == 'Food':
        name = 'Dining & Drinks'
    return CATEGORY_ICONS.get(name, CATEGORY_ICONS['Other'])
