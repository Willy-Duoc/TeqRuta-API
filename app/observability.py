"""Integración de observabilidad (Sentry) para la API.

La inicialización es opcional: si `SENTRY_DSN` está vacío no se carga ningún
cliente ni se envía información. En producción se recomienda definir también
`SENTRY_ENVIRONMENT` y `SENTRY_RELEASE`.
"""

from __future__ import annotations

from flask import Flask


def init_sentry(app: Flask) -> bool:
    """Inicializa Sentry si hay DSN. Devuelve True cuando quedó activo."""

    dsn = str(app.config.get("SENTRY_DSN") or "").strip()
    if not dsn:
        app.logger.debug("Sentry desactivado: SENTRY_DSN vacío")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except ImportError:  # pragma: no cover - requirements incluye sentry-sdk
        app.logger.warning("Sentry no está instalado; se omite la observabilidad")
        return False

    def _before_send(event, hint):
        exc_info = hint.get("exc_info") if hint else None
        if exc_info and issubclass(exc_info[0], (KeyboardInterrupt, SystemExit)):
            return None
        return event

    sentry_sdk.init(
        dsn=dsn,
        environment=str(app.config.get("SENTRY_ENVIRONMENT") or "production"),
        release=str(app.config.get("SENTRY_RELEASE") or "") or None,
        traces_sample_rate=float(app.config.get("SENTRY_TRACES_SAMPLE_RATE") or 0.0),
        profiles_sample_rate=0.0,
        send_default_pii=bool(app.config.get("SENTRY_SEND_DEFAULT_PII", False)),
        max_request_body_size="never",
        attach_stacktrace=True,
        integrations=[FlaskIntegration(), SqlalchemyIntegration()],
        before_send=_before_send,
    )
    app.logger.info(
        "Sentry activo (environment=%s, release=%s)",
        app.config.get("SENTRY_ENVIRONMENT"),
        app.config.get("SENTRY_RELEASE"),
    )
    return True
