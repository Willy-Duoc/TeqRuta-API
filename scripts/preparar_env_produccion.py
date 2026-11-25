#!/usr/bin/env python3
"""Genera `.env.production` desde la plantilla con secretos aleatorios.

Uso (lo invoca `make prod-env`):

    python3 scripts/preparar_env_produccion.py

No sobreescribe un archivo existente. La contraseña de PostgreSQL se genera en
hexadecimal para que sea segura al insertarla en una URL sin codificar.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESTINO = ROOT / ".env.production"
EJEMPLO = ROOT / ".env.production.example"

MARCADOR_SECRET = "SECRET_KEY=cambia-esta-clave-en-produccion"
MARCADOR_JWT = "JWT_SECRET_KEY=cambia-este-secreto-jwt-en-produccion"
MARCADOR_PG = "POSTGRES_PASSWORD=cambia-esta-clave-postgres"


def main() -> int:
    if DESTINO.exists():
        print("[prod-env] .env.production ya existe; no se modifica.")
        return 0
    if not EJEMPLO.exists():
        print(f"[prod-env] No se encontró {EJEMPLO}", file=sys.stderr)
        return 1

    lineas: list[str] = []
    for linea in EJEMPLO.read_text(encoding="utf-8").splitlines():
        if linea.startswith(MARCADOR_SECRET):
            lineas.append(f"SECRET_KEY={secrets.token_urlsafe(48)}")
        elif linea.startswith(MARCADOR_JWT):
            lineas.append(f"JWT_SECRET_KEY={secrets.token_urlsafe(48)}")
        elif linea.startswith(MARCADOR_PG):
            lineas.append(f"POSTGRES_PASSWORD={secrets.token_hex(24)}")
        else:
            lineas.append(linea)

    DESTINO.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    try:
        DESTINO.chmod(0o600)
    except OSError:  # pragma: no cover - sistemas sin permisos POSIX
        pass

    print("[prod-env] .env.production creado con SECRET_KEY, JWT y PostgreSQL aleatorios.")
    print("[prod-env] Revisa SENTRY_DSN y los puertos antes de make prod-up.")
    print("[prod-env] Certificados TLS: make prod-cert (pruebas) o Let's Encrypt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
