"""Configuración centralizada de la API TeqRuta.

Todos los valores podemos sobreescribirlos mediante variables de entorno,
lo que permite usar la misma base de código en local, con Ngrok o en producción.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

try:  # python-dotenv es parte de requirements; el fallback mantiene el API usable sin él.
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover - solo si se omite python-dotenv
    pass


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def normalize_database_url(url: str) -> str:
    """Normaliza URLs de PostgreSQL para usar el driver psycopg 3.

    Railway, Heroku y otros proveedores entregan `postgres://`; SQLAlchemy 2.x
    necesita un driver explícito. Las URLs SQLite se dejan intactas.
    """

    value = (url or "").strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


def _engine_options(database_url: str) -> dict:
    """Opciones de pool adecuadas para SQLite o PostgreSQL."""

    if database_url.startswith("sqlite:"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "280")),
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
    }


class Config:
    """Configuración base."""

    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()

    # Servidor: por defecto solo loopback. Ngrok se conecta a 127.0.0.1 y es el
    # único punto de entrada público; el puerto interno nunca se expone en la LAN.
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))
    # Confiar en X-Forwarded-* solo tiene sentido si el puerto está en loopback
    # (Ngrok, Nginx o proxy local). Si se expone en LAN, se desactiva por defecto.
    TRUST_PROXY = _bool("TRUST_PROXY", HOST in {"127.0.0.1", "localhost", "::1"})
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-teqruta-cambiar")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_EXPIRE_HOURS", "8")))

    # Sesión del dashboard web (independiente del JWT de la app móvil).
    SESSION_COOKIE_NAME = "teqruta_admin"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.getenv("SESSION_HOURS", "8")))

    # Límite de cuerpo: suficiente para fotos comprimidas o cargas administrativas.
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "16")) * 1024 * 1024

    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.getenv("DATABASE_URL", "sqlite:///teqruta.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)
    AUTO_CREATE_DB = _bool("AUTO_CREATE_DB", True)
    SEED_DEMO_USERS = _bool("SEED_DEMO_USERS", True)

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")

    # Observabilidad: si SENTRY_DSN está vacío, el SDK no se inicializa.
    SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
    SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", APP_ENV)
    SENTRY_RELEASE = os.getenv("SENTRY_RELEASE", "teqruta-api@1.0.0")
    SENTRY_TRACES_SAMPLE_RATE = max(
        0.0, min(1.0, float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")))
    )
    SENTRY_SEND_DEFAULT_PII = _bool("SENTRY_SEND_DEFAULT_PII", False)

    # Fuente pública de precios de combustible.
    FUEL_PRICE_URL = os.getenv("FUEL_PRICE_URL", "https://ahorrahogar.cl/datos/datos.json")
    FUEL_PRICE_TIMEOUT = float(os.getenv("FUEL_PRICE_TIMEOUT", "5"))
    FUEL_PRICE_CACHE_HOURS = int(os.getenv("FUEL_PRICE_CACHE_HOURS", "24"))
    FUEL_REGION_CODE = os.getenv("FUEL_REGION_CODE", "8")  # 8 = Biobío
    FUEL_DEFAULT_PRICE = float(os.getenv("FUEL_DEFAULT_PRICE", "1597"))
    COSTO_COMBUSTIBLE_TIPO = os.getenv("COSTO_COMBUSTIBLE_TIPO", "93")

    # Motor de cálculo centralizado.
    DEFAULT_RENDIMIENTO_KM_L = float(os.getenv("DEFAULT_RENDIMIENTO_KM_L", "10"))
    DESVIACION_UMBRAL_PCT = float(os.getenv("DESVIACION_UMBRAL_PCT", "10"))


class TestingConfig(Config):
    """Configuración usada por pytest: sin red y con BD en memoria o PostgreSQL.

    Define `TEST_DATABASE_URL` para ejecutar la misma suite contra PostgreSQL
    (lo hace el pipeline de CI y `make test-postgres`).
    """

    TESTING = True
    APP_ENV = "testing"
    HOST = "127.0.0.1"
    PORT = 5000
    TRUST_PROXY = True
    SQLALCHEMY_DATABASE_URI = normalize_database_url(
        os.getenv("TEST_DATABASE_URL", "sqlite:///:memory:")
    )
    SQLALCHEMY_ENGINE_OPTIONS = (
        {} if SQLALCHEMY_DATABASE_URI.startswith("sqlite:") else _engine_options(
            SQLALCHEMY_DATABASE_URI
        )
    )
    FUEL_PRICE_URL = ""
    SEED_DEMO_USERS = True
    AUTO_CREATE_DB = True
    JWT_SECRET_KEY = "testing-jwt-secret-sufficiently-long-1234567890"
    SECRET_KEY = "testing-secret"
    SESSION_COOKIE_SECURE = False
    SENTRY_DSN = ""
