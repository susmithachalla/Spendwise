"""Request-scoped SQLite connections for the browser expense workspace."""
import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if 'db' not in g:
        Path(current_app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
        g.db.executescript('''
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
            CREATE INDEX IF NOT EXISTS expenses_owner_date
            ON expenses(owner_token, expense_date DESC, id DESC);
        ''')
    return g.db


def close_db(error=None):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()
