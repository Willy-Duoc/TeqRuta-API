#!/usr/bin/env bash
# Genera un certificado autofirmado para pruebas locales del stack Docker.
#
#   bash deploy/generar_certificado.sh [dominio]
#
# Para producción real usa Let's Encrypt (certbot) u otro certificado válido y
# reemplaza fullchain.pem / privkey.pem en deploy/certs/. El directorio está
# ignorado por Git: los certificados nunca se versionan.
set -euo pipefail

DOMINIO="${1:-localhost}"
DESTINO="$(cd "$(dirname "$0")" && pwd)/certs"

mkdir -p "$DESTINO"
chmod 700 "$DESTINO"

if [[ -f "$DESTINO/fullchain.pem" && -f "$DESTINO/privkey.pem" ]]; then
  echo "[cert] Ya existen certificados en $DESTINO; no se sobreescriben."
  exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -keyout "$DESTINO/privkey.pem" \
  -out "$DESTINO/fullchain.pem" \
  -subj "/CN=${DOMINIO}" \
  -addext "subjectAltName=DNS:${DOMINIO},DNS:localhost,IP:127.0.0.1"

chmod 600 "$DESTINO/privkey.pem" "$DESTINO/fullchain.pem"

cat <<EOF
[cert] Certificado autofirmado creado para ${DOMINIO} en $DESTINO
[cert] El navegador mostrará una advertencia: es esperado en pruebas locales.
[cert] Para producción usa un certificado válido (Let's Encrypt).
EOF
