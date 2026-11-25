"""Fábrica de la aplicación Flask TeqRuta.

Estructura basada en Blueprints (Auth, Viajes, Reportes, Mantenedores y Admin)
según el requisito de mantenibilidad de la ERS.
"""

from __future__ import annotations

import os

import click
from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .errors import register_error_handlers
from .extensions import cors, db
from .observability import init_sentry
from .seed import seed_database

_SECRETOS_DE_EJEMPLO = {
    "dev-secret-teqruta-cambiar",
    "cambia-esta-clave-en-produccion",
    "testing-secret",
}


def create_app(config_object=None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    if (
        app.config.get("APP_ENV") == "production"
        and app.config.get("SECRET_KEY") in _SECRETOS_DE_EJEMPLO
    ):
        app.logger.warning(
            "SECRET_KEY de ejemplo en producción. Define una clave aleatoria en .env"
        )

    # Ngrok/Nginx terminan TLS y reenvían X-Forwarded-Proto/Host/For. Sin esto
    # Flask generaría URLs http:// y vería 127.0.0.1 como cliente.
    if app.config.get("TRUST_PROXY", True):
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
        )

    app.json.sort_keys = False
    init_sentry(app)
    db.init_app(app)
    cors.init_app(app, origins=app.config["CORS_ORIGINS"])

    register_error_handlers(app)
    register_blueprints(app)
    register_cli(app)

    @app.after_request
    def _cabeceras_seguridad(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    with app.app_context():
        if app.config.get("AUTO_CREATE_DB", True):
            db.create_all()
            if app.config.get("SEED_DEMO_USERS"):
                seed_database(app)

    return app


def register_blueprints(app: Flask) -> None:
    from .admin.routes import bp as admin_bp
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
    app.register_blueprint(admin_bp, url_prefix="/admin")


def register_cli(app: Flask) -> None:
    """Comandos para preparar una base PostgreSQL sin datos demo."""

    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Crea las tablas y, si está activo, carga los datos demo."""

        db.create_all()
        if app.config.get("SEED_DEMO_USERS"):
            seed_database(app)
            click.echo("Tablas creadas y datos demo cargados.")
        else:
            click.echo("Tablas creadas (sin datos demo).")

    @app.cli.command("create-admin")
    @click.option("--email", prompt="Email", help="Correo del administrador")
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
        help="Contraseña (mínimo 8 caracteres)",
    )
    @click.option("--nombre", prompt="Nombre", help="Nombre visible")
    def create_admin_command(email: str, password: str, nombre: str) -> None:
        """Crea un usuario administrador en una base existente."""

        from .models import User
        from .security import hash_password

        email = email.strip().lower()
        nombre = nombre.strip()
        if not email or not nombre:
            raise click.ClickException("Email y nombre son obligatorios")
        if len(password) < 8:
            raise click.ClickException("La contraseña debe tener al menos 8 caracteres")
        if User.query.filter_by(email=email).first():
            raise click.ClickException(f"El email {email} ya está registrado")

        db.session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                nombre=nombre,
                rol="admin",
                cargo="Administrador del Sistema",
                activo=True,
            )
        )
        db.session.commit()
        click.echo(f"Administrador {email} creado.")
