"""Pruebas del orquestador de túnel sin depender de un token real de Ngrok."""

from __future__ import annotations

import threading

import pytest
from werkzeug.serving import make_server

from app import create_app
from app.config import TestingConfig
from scripts import tunel


def test_url_publica_se_lee_del_agente(monkeypatch):
    monkeypatch.setattr(
        tunel,
        "_http_json",
        lambda *args, **kwargs: (
            200,
            {
                "tunnels": [
                    {"public_url": "http://localhost:5000", "proto": "http"},
                    {"public_url": "https://teqruta-test.ngrok-free.app", "proto": "https"},
                ]
            },
        ),
    )

    assert tunel.leer_url_publica() == "https://teqruta-test.ngrok-free.app"


def test_ruta_app_android_desde_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("TEQRUTA_APP_DIR", str(tmp_path))

    assert tunel.ruta_app_android() == tmp_path


def test_actualizar_local_properties_preserva_sdk_dir(tmp_path, monkeypatch):
    props = tmp_path / "local.properties"
    props.write_text(
        "sdk.dir=/opt/android-sdk\n"
        "teqrutaApiBaseUrl=http://10.0.2.2:8080/\n"
        "otra.propiedad=1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tunel, "ruta_app_android", lambda: tmp_path)

    resultado = tunel.actualizar_local_properties("https://abc.ngrok-free.app/")

    assert resultado == props
    texto = props.read_text(encoding="utf-8")
    assert "sdk.dir=/opt/android-sdk" in texto
    assert "otra.propiedad=1" in texto
    assert "teqrutaApiBaseUrl=https://abc.ngrok-free.app/" in texto
    assert texto.count("teqrutaApiBaseUrl=") == 1


def test_actualizar_local_properties_agrega_si_no_existe(tmp_path, monkeypatch):
    props = tmp_path / "local.properties"
    monkeypatch.setattr(tunel, "ruta_app_android", lambda: tmp_path)

    tunel.actualizar_local_properties("https://nuevo.ngrok-free.app")

    assert props.read_text(encoding="utf-8") == (
        "teqrutaApiBaseUrl=https://nuevo.ngrok-free.app/\n"
    )


def test_actualizar_local_properties_sin_proyecto_android(tmp_path, monkeypatch):
    monkeypatch.setattr(tunel, "ruta_app_android", lambda: tmp_path / "no-existe")

    assert tunel.actualizar_local_properties("https://nuevo.ngrok-free.app") is None


def test_preparar_config_ngrok_no_expone_token_en_comando(tmp_path, monkeypatch):
    config = tmp_path / "ngrok.yml"
    monkeypatch.setattr(tunel, "RUN_DIR", tmp_path)
    monkeypatch.setattr(tunel, "NGROK_CONFIG", config)
    monkeypatch.setenv("NGROK_AUTHTOKEN", "token-de-prueba")

    assert tunel.preparar_config_ngrok() == config
    texto = config.read_text(encoding="utf-8")
    assert "token-de-prueba" in texto
    assert "web_addr: 127.0.0.1:4040" in texto


class _SmokeConfig(TestingConfig):
    """SQLite en archivo para que el servidor y el test compartan la BD."""

    SQLALCHEMY_DATABASE_URI = ""
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"check_same_thread": False}}


def test_smoke_end_to_end_contra_servidor_local(tmp_path):
    class SmokeConfig(_SmokeConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'smoke.db'}"

    app = create_app(SmokeConfig)
    server = make_server("127.0.0.1", 0, app)
    hilo = threading.Thread(target=server.serve_forever, daemon=True)
    hilo.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        resultados = tunel.ejecutar_smoke(base)
    finally:
        server.shutdown()
        server.server_close()
        hilo.join(timeout=5)

    fallos = [item for item in resultados if not item["ok"]]
    assert not fallos, fallos
    assert len(resultados) >= 11
    assert any("URL pública sin puerto" in item["nombre"] for item in resultados)


def test_smoke_reporta_fallo_si_no_hay_servidor():
    resultados = tunel.ejecutar_smoke("http://127.0.0.1:1", incluir_limpieza=False)

    assert resultados
    assert resultados[0]["nombre"] == "Salud del API"
    assert resultados[0]["ok"] is False
