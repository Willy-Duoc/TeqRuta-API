#!/usr/bin/env python3
"""Genera `.env` a partir de `.env.example` sin sobreescribir uno existente.

Uso normal (lo invoca `make setup`):

    python3 scripts/preparar_env.py

Si defines `NGROK_AUTHTOKEN` y/o `NGROK_DOMAIN` en el entorno, se copian al
archivo para que `make publicar` funcione sin edición manual.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / ".env"
EJEMPLO = ROOT / ".env.example"

MARCADOR_SECRET = "SECRET_KEY=cambia-esta-clave-en-produccion"
MARCADOR_JWT = "JWT_SECRET_KEY=cambia-este-secreto-jwt-en-produccion"


def crear_env(
    destino: Path,
    ejemplo: Path,
    *,
    token: str = "",
    dominio: str = "",
) -> bool:
    """Crea `destino` desde `ejemplo`. Devuelve False si ya existía."""

    if destino.exists():
        return False

    texto = ejemplo.read_text(encoding="utf-8")
    lineas: list[str] = []
    for linea in texto.splitlines():
        if linea.startswith(MARCADOR_SECRET):
            lineas.append(f"SECRET_KEY={secrets.token_urlsafe(48)}")
        elif linea.startswith(MARCADOR_JWT):
            lineas.append(f"JWT_SECRET_KEY={secrets.token_urlsafe(48)}")
        elif linea.startswith("NGROK_AUTHTOKEN=") and token.strip():
            lineas.append(f"NGROK_AUTHTOKEN={token.strip()}")
        elif linea.startswith("NGROK_DOMAIN=") and dominio.strip():
            lineas.append(f"NGROK_DOMAIN={dominio.strip().removeprefix('https://')}")
        else:
            lineas.append(linea)

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    try:
        destino.chmod(0o600)
    except OSError:  # pragma: no cover - sistemas sin permisos POSIX
        pass
    return True


def main() -> int:
    if DESTINO.exists():
        print("[env] .env ya existe; no se modifica.")
        return 0

    if not EJEMPLO.exists():
        print(f"[env] No se encontró {EJEMPLO}", file=sys.stderr)
        return 1

    creado = crear_env(
        DESTINO,
        EJEMPLO,
        token=os.getenv("NGROK_AUTHTOKEN", ""),
        dominio=os.getenv("NGROK_DOMAIN", ""),
    )
    if not creado:  # pragma: no cover - cubierto por la comprobación anterior
        print("[env] .env ya existe; no se modifica.")
        return 0

    print("[env] .env creado con SECRET_KEY y JWT_SECRET_KEY aleatorios.")
    if not os.getenv("NGROK_AUTHTOKEN", "").strip():
        print("[env] Falta NGROK_AUTHTOKEN: edita .env antes de make publicar.")
    else:
        print("[env] NGROK_AUTHTOKEN copiado desde el entorno.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
