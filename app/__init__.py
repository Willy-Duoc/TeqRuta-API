"""Fábrica de la aplicación Flask TeqRuta.

Estructura basada en Blueprints (Auth, Viajes, Reportes, Mantenedores)
según el requisito de mantenibilidad de la ERS.
"""

from __future__ import annotations

import os

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .errors import register_error_handlers
from .extensions import cors, db
from .seed import seed_database


def create_app(config_object=None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Ngrok termina TLS y reenvía X-Forwarded-Proto/Host/For. Sin esto Flask
    # generaría URLs http:// y vería 127.0.0.1 como cliente.
    if app.config.get("TRUST_PROXY", True):
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
        )

    app.json.sort_keys = False
    db.init_app(app)
    cors.init_app(app, origins=app.config["CORS_ORIGINS"])

    register_error_handlers(app)
    register_blueprints(app)

    @app.after_request
    def _cabeceras_seguridad(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    with app.app_context():
        db.create_all()
        if app.config.get("SEED_DEMO_USERS"):
            seed_database(app)

    return app


def register_blueprints(app: Flask) -> None:
    from .api import bp as api_bp
    from .auth.routes import bp as auth_bp
    from .mantenedores.routes import bp as mantenedores_bp
    from .reportes.routes import bp as reportes_bp
    from .viajes.routes import bp as viajes_bp

    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(viajes_bp, url_prefix="/api/viajes")
    app.register_blueprint(reportes_bp, url_prefix="/api/reportes")
    app.register_blueprint(mantenedores_bp, url_prefix="/api/mantenedores")
