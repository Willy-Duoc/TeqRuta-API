"""Pruebas de configuración de producción, Sentry y CLI administrativa."""

from __future__ import annotations

from app import create_app
from app.config import TestingConfig, normalize_database_url
from app.models import User


def test_normaliza_urls_de_postgresql():
    assert (
        normalize_database_url("postgres://u:p@host:5432/db")
        == "postgresql+psycopg://u:p@host:5432/db"
    )
    assert (
        normalize_database_url("postgresql://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )
    assert (
        normalize_database_url("postgresql+psycopg://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )
    assert normalize_database_url("sqlite:///teqruta.db") == "sqlite:///teqruta.db"


def test_sentry_se_inicializa_solo_con_dsn(monkeypatch):
    import sentry_sdk

    llamadas: list[dict] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: llamadas.append(kwargs))

    class SinSentry(TestingConfig):
        SENTRY_DSN = ""

    create_app(SinSentry)
    assert llamadas == []

    class ConSentry(TestingConfig):
        SENTRY_DSN = "https://public@example.ingest.sentry.io/1"
        SENTRY_ENVIRONMENT = "test"
        SENTRY_RELEASE = "teqruta-api@test"
        SENTRY_TRACES_SAMPLE_RATE = 0.25
        SENTRY_SEND_DEFAULT_PII = False

    create_app(ConSentry)
    assert len(llamadas) == 1
    opciones = llamadas[0]
    assert opciones["dsn"] == ConSentry.SENTRY_DSN
    assert opciones["environment"] == "test"
    assert opciones["release"] == "teqruta-api@test"
    assert opciones["traces_sample_rate"] == 0.25
    assert opciones["send_default_pii"] is False
    assert opciones["max_request_body_size"] == "never"
    assert opciones["before_send"] is not None


def test_cli_create_admin(app):
    runner = app.test_cli_runner()
    resultado = runner.invoke(
        args=[
            "create-admin",
            "--email",
            "cli-admin@teqmed.cl",
            "--password",
            "ClaveSegura123",
            "--nombre",
            "Admin CLI",
        ]
    )
    assert resultado.exit_code == 0, resultado.output
    with app.app_context():
        creado = User.query.filter_by(email="cli-admin@teqmed.cl").one()
        assert creado.rol == "admin"
        assert creado.activo is True
