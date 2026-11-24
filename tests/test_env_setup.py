"""Pruebas del generador de `.env` para instalaciones nuevas."""

from __future__ import annotations

import stat

from scripts.preparar_env import crear_env


EJEMPLO = """\
HOST=127.0.0.1
PORT=5000
SECRET_KEY=cambia-esta-clave-en-produccion
JWT_SECRET_KEY=cambia-este-secreto-jwt-en-produccion
NGROK_AUTHTOKEN=
NGROK_DOMAIN=
"""


def test_crear_env_genera_secretos_y_copia_token(tmp_path):
    ejemplo = tmp_path / ".env.example"
    ejemplo.write_text(EJEMPLO, encoding="utf-8")
    destino = tmp_path / ".env"

    assert crear_env(destino, ejemplo, token="token-demo", dominio="https://demo.ngrok-free.dev")

    texto = destino.read_text(encoding="utf-8")
    assert "cambia-esta-clave-en-produccion" not in texto
    assert "cambia-este-secreto-jwt-en-produccion" not in texto
    assert "NGROK_AUTHTOKEN=token-demo" in texto
    assert "NGROK_DOMAIN=demo.ngrok-free.dev" in texto
    assert stat.S_IMODE(destino.stat().st_mode) == 0o600


def test_crear_env_no_sobreescribe_uno_existente(tmp_path):
    ejemplo = tmp_path / ".env.example"
    ejemplo.write_text(EJEMPLO, encoding="utf-8")
    destino = tmp_path / ".env"
    destino.write_text("SECRET_KEY=personalizada\n", encoding="utf-8")

    assert crear_env(destino, ejemplo, token="no-debe-entrar") is False
    assert destino.read_text(encoding="utf-8") == "SECRET_KEY=personalizada\n"
