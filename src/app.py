from flask import Flask, redirect, render_template, request, session, url_for
from datetime import timedelta
from pathlib import Path
import os
import json
import secrets
import re
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash

from src.currencies import money
from src.database.db import close_db, get_db
from src.expenses import expenses_bp
from src.income import income_bp
from src.investments import investments_bp
from src.periods import prepare_period, period_context

app = Flask(__name__, instance_path=str(Path(__file__).resolve().parent.parent / 'instance'))

# Keep the signing key stable across restarts so browser workspaces survive.
instance = Path(app.instance_path)
instance.mkdir(parents=True, exist_ok=True)
secret_path = instance / '.secret_key'
if not os.environ.get('SPENDWISE_SECRET_KEY'):
    try:
        descriptor = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as secret_file:
            secret_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
app.config.update(
    SECRET_KEY=os.environ.get('SPENDWISE_SECRET_KEY') or secret_path.read_text(),
    REPORTING_CURRENT_RATES=json.loads(os.environ.get('SPENDWISE_USD_RATES', '{}')),
    REPORTING_HISTORICAL_RATES={},
    DATABASE=str(instance / 'spendwise.sqlite'),
    SESSION_COOKIE_NAME='spendwise_session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=365),
    MAX_CONTENT_LENGTH=64 * 1024,
)
app.before_request(prepare_period)
app.context_processor(period_context)
app.teardown_appcontext(close_db)
app.jinja_env.globals['money'] = money
app.register_blueprint(expenses_bp)
app.register_blueprint(income_bp)
app.register_blueprint(investments_bp)


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


def auth_csrf():
    if 'auth_csrf' not in session:
        session['auth_csrf'] = secrets.token_urlsafe(32)
    return session['auth_csrf']


def valid_auth_csrf():
    return secrets.compare_digest(request.form.get('csrf_token', '').encode(),
                                  auth_csrf().encode())


def sign_in(user):
    session.clear()
    session['user_id'] = user['id']
    session['expense_owner'] = user['owner_token']
    session.permanent = True
    return redirect(url_for('expenses.index'), code=303)


@app.route("/register", methods=['GET', 'POST'])
def register():
    error = None
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    if request.method == 'POST':
        password = request.form.get('password', '')
        if not valid_auth_csrf():
            error = 'This form has expired. Please try again.'
        elif not 1 <= len(name) <= 100:
            error = 'Enter your full name (up to 100 characters).'
        elif len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            error = 'Enter a valid email address.'
        elif not 8 <= len(password) <= 128 or not password.strip():
            error = 'Use a password between 8 and 128 characters.'
        else:
            db = get_db()
            if db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
                error = 'An account with this email already exists. Please sign in.'
            else:
                owner = secrets.token_urlsafe(32)
                try:
                    with db:
                        cursor = db.execute(
                            'INSERT INTO users (name, email, password_hash, owner_token) VALUES (?, ?, ?, ?)',
                            (name, email, generate_password_hash(password), owner))
                        # Only claim anonymous expenses, never another signed-in account's.
                        if not session.get('user_id') and session.get('expense_owner'):
                            db.execute('UPDATE expenses SET owner_token = ? WHERE owner_token = ?',
                                       (owner, session['expense_owner']))
                    return sign_in({'id': cursor.lastrowid, 'owner_token': owner})
                except sqlite3.IntegrityError:
                    error = 'An account with this email already exists. Please sign in.'
    return render_template('register.html', error=error, name=name, email=email,
                           csrf_token=auth_csrf()), (400 if error else 200)


@app.route("/login", methods=['GET', 'POST'])
def login():
    error = None
    email = request.form.get('email', '').strip().lower()
    if request.method == 'POST':
        password = request.form.get('password', '')
        if not valid_auth_csrf():
            error = 'This form has expired. Please try again.'
        elif not email or len(email) > 254 or not password or len(password) > 128:
            error = 'Enter your email address and password (up to 128 characters).'
        else:
            user = get_db().execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                return sign_in(user)
            error = 'Incorrect email or password. Please try again.'
    return render_template('login.html', error=error, email=email,
                           csrf_token=auth_csrf()), (400 if error else 200)


@app.route("/terms", methods=["GET"])
def terms():
    return render_template("terms.html")


@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout", methods=['POST'])
def logout():
    if not valid_auth_csrf():
        return 'This form has expired. Reload the page and try again.', 400
    session.clear()
    return redirect(url_for('landing'), code=303)


app.jinja_env.globals['auth_csrf'] = auth_csrf


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
