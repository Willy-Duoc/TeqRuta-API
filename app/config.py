"""Configuración centralizada de la API TeqRuta.

Todos los valores podemos sobreescribirlos mediante variables de entorno,
lo que permite usar la misma base de código en local, con Ngrok o en producción.
"""

from __future__ import annotations

import os
from datetime import timedelta


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Configuración base."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-teqruta-cambiar")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_EXPIRE_HOURS", "8")))

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///teqruta.db")
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        # SQLAlchemy 2.x usa el driver psycopg 3 por defecto.
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    if SQLALCHEMY_DATABASE_URI.startswith("sqlite:"):
        SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    SEED_DEMO_USERS = _bool("SEED_DEMO_USERS", True)
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")

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
    """Configuración usada por pytest: sin red y con BD en memoria."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    FUEL_PRICE_URL = ""
    SEED_DEMO_USERS = True
    JWT_SECRET_KEY = "testing-jwt-secret-sufficiently-long-1234567890"
    SECRET_KEY = "testing-secret"
