"""Servidor de desarrollo.

    python run.py

Por defecto escucha solo en 127.0.0.1 para que el puerto interno no quede
expuesto en la red. La salida pública se gestiona con Ngrok:

    python scripts/tunel.py iniciar

Si de verdad necesitas exponer el puerto en la LAN (sin túnel), usa
HOST=0.0.0.0 y idealmente TRUST_PROXY=false.
"""

from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}
    app.run(
        host=app.config.get("HOST", "127.0.0.1"),
        port=int(app.config.get("PORT", 5000)),
        debug=debug,
    )
