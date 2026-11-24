#!/usr/bin/env bash
# Instala el agente de Ngrok dentro de .tools/ (sin sudo y sin tocar el sistema).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/.tools"
mkdir -p "$DEST"

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$OS-$ARCH" in
  linux-x86_64)        URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz"; EXT="tgz" ;;
  linux-aarch64|linux-arm64) URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-arm64.tgz"; EXT="tgz" ;;
  darwin-x86_64)       URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-amd64.zip"; EXT="zip" ;;
  darwin-arm64)        URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-arm64.zip"; EXT="zip" ;;
  *)
    echo "Sistema no soportado por este instalador: $OS-$ARCH" >&2
    echo "Descarga el binario manualmente desde https://ngrok.com/download" >&2
    exit 1
    ;;
esac

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "[ngrok] Descargando agente para $OS-$ARCH…"
curl -fsSL "$URL" -o "$TMP/ngrok.$EXT"

if [ "$EXT" = "zip" ]; then
  unzip -q "$TMP/ngrok.$EXT" -d "$TMP"
else
  tar -xzf "$TMP/ngrok.$EXT" -C "$TMP"
fi

install -m 0755 "$TMP/ngrok" "$DEST/ngrok"
echo "[ngrok] Instalado en $DEST/ngrok"
"$DEST/ngrok" version

cat <<'EOF'

Siguiente paso:
  1. Copia .env.example a .env si aún no existe.
  2. Agrega tu token: NGROK_AUTHTOKEN=...
     (https://dashboard.ngrok.com/get-started/your-authtoken)
  3. Ejecuta: python scripts/tunel.py iniciar
EOF
