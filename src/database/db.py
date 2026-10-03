"""Request-scoped SQLite connections for the browser expense workspace."""
import sqlite3
from pathlib import Path

from flask import current_app, g

from src.categories import LEGACY_MAPPINGS


def get_db():
    if 'db' not in g:
        Path(current_app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
        g.db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                owner_token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY,
                owner_token TEXT NOT NULL,
                expense_date TEXT NOT NULL,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                currency TEXT NOT NULL CHECK(length(currency) = 3),
                fraction_digits INTEGER NOT NULL CHECK(fraction_digits BETWEEN 0 AND 4),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS account_preferences (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                income_enabled INTEGER NOT NULL DEFAULT 0 CHECK(income_enabled IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS income (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                income_date TEXT NOT NULL,
                category TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                amount_minor INTEGER NOT NULL CHECK(amount_minor >= 0),
                currency TEXT NOT NULL CHECK(length(currency) = 3),
                fraction_digits INTEGER NOT NULL CHECK(fraction_digits BETWEEN 0 AND 4),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS investments (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                investment_date TEXT NOT NULL,
                investment_type TEXT NOT NULL CHECK(investment_type IN ('Stocks','ETFs','Mutual Funds','Other')),
                notes TEXT NOT NULL DEFAULT '',
                amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                currency TEXT NOT NULL CHECK(length(currency) = 3),
                fraction_digits INTEGER NOT NULL CHECK(fraction_digits BETWEEN 0 AND 4),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS reporting_rates (
                currency TEXT NOT NULL, requested_date TEXT NOT NULL, units_per_usd TEXT NOT NULL,
                rate_date TEXT NOT NULL, source TEXT NOT NULL, PRIMARY KEY(currency, requested_date)
            );
            CREATE TABLE IF NOT EXISTS reporting_conversions (
                fingerprint TEXT PRIMARY KEY, kind TEXT NOT NULL, transaction_id INTEGER NOT NULL,
                original_currency TEXT NOT NULL, original_minor TEXT NOT NULL, original_digits INTEGER NOT NULL,
                transaction_date TEXT NOT NULL, units_per_usd TEXT NOT NULL, rate_date TEXT NOT NULL,
                source TEXT NOT NULL, usd_minor TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS investments_user_date ON investments(user_id, investment_date DESC, id DESC);
            CREATE INDEX IF NOT EXISTS income_user_date ON income(user_id, income_date DESC, id DESC);
            CREATE INDEX IF NOT EXISTS expenses_owner_date
            ON expenses(owner_token, expense_date DESC, id DESC);
        ''')
        columns = {row['name'] for row in g.db.execute('PRAGMA table_info(investments)')}
        if 'subtype' not in columns:
            g.db.execute("ALTER TABLE investments ADD COLUMN subtype TEXT NOT NULL DEFAULT 'Contribution' CHECK(subtype IN ('Contribution','Return','Withdrawal','Dividend','Interest','Capital gain','Other income'))")
            g.db.commit()
        # Idempotent renames preserve IDs, amounts, and ownership. Food and Bills
        # are deliberately absent: their intended category cannot be inferred.
        with g.db:
            for old, new in LEGACY_MAPPINGS.items():
                g.db.execute('UPDATE expenses SET category = ? WHERE category = ?', (new, old))
    return g.db


def close_db(error=None):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()
