"""Pruebas de la publicación detrás de Ngrok (proxy, cabeceras y loopback)."""

from __future__ import annotations

from flask import request

from app.config import Config


def test_health_es_publico_y_sin_puerto_expuesto(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"] == "ok"
    # El endpoint no revela el puerto interno ni la URL local.
    assert "5000" not in response.get_data(as_text=True)


def test_proxy_fix_respeta_https_y_host_de_ngrok(app):
    @app.get("/_test/entorno")
    def _entorno():
        return {"url": request.url_root, "remoto": request.remote_addr}

    client = app.test_client()
    response = client.get(
        "/_test/entorno",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "teqruta.ngrok-free.app",
            "X-Forwarded-For": "203.0.113.9",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["url"] == "https://teqruta.ngrok-free.app/"
    assert data["remoto"] == "203.0.113.9"


def test_cabeceras_de_seguridad_en_https(client):
    response = client.get(
        "/api/health",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "teqruta.ngrok-free.app",
        },
    )

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Strict-Transport-Security"].startswith("max-age=")


def test_host_por_defecto_es_loopback():
    assert Config.HOST == "127.0.0.1"
    assert Config.TRUST_PROXY is True
