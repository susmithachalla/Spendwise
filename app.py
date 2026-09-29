from flask import Flask, render_template
from datetime import timedelta
from pathlib import Path
import os
import secrets

from currencies import money
from database.db import close_db
from expenses import expenses_bp

app = Flask(__name__)

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
    DATABASE=str(instance / 'spendwise.sqlite'),
    SESSION_COOKIE_NAME='spendwise_session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=365),
    MAX_CONTENT_LENGTH=64 * 1024,
)
app.teardown_appcontext(close_db)
app.jinja_env.globals['money'] = money
app.register_blueprint(expenses_bp)


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/terms", methods=["GET"])
def terms():
    return render_template("terms.html")


@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
