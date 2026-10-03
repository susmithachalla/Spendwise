"""Compatibility launcher; application source lives in src."""
from src.app import app

if __name__ == "__main__":
    app.run(debug=True, port=5001)
