"""WSGI entry point. `FLASK_APP=wsgi.py flask run --port 8000` finds `app`."""

from app import create_app

app = create_app()

if __name__ == "__main__":  # pragma: no cover
    app.run(port=8000)
