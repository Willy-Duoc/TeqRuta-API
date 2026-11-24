"""Punto de entrada WSGI para Gunicorn / servidores de producción.

Detrás de Ngrok (o de un reverse proxy local) el puerto debe quedar en loopback:

    gunicorn --bind 127.0.0.1:5000 wsgi:app

Solo si el proxy corre en otra máquina de una red confiable usa 0.0.0.0.
"""

from app import create_app

app = create_app()
