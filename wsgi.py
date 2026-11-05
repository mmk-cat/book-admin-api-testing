"""WSGI entry point used by Docker/gunicorn."""

from book_admin.app import create_app

app = create_app()
