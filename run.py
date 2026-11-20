"""Servidor de desarrollo.

    python run.py

Luego expón este puerto con Ngrok:

    ngrok http 5000
"""

from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "true").strip().lower() in {"1", "true", "yes", "on"}
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "5000")),
        debug=debug,
    )
