"""Punto de entrada WSGI para Gunicorn / servidores de producción.

    gunicorn --bind 0.0.0.0:5000 wsgi:app
"""

from app import create_app

app = create_app()
