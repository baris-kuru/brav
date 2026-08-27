#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="python3"
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

CERT_DIR="$ROOT_DIR/data/certs"
CERT_FILE="$CERT_DIR/localhost.crt"
KEY_FILE="$CERT_DIR/localhost.key"
HOST="${CAFE_HOST:-127.0.0.1}"
PORT="${CAFE_HTTPS_PORT:-8443}"

mkdir -p "$CERT_DIR"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days 365 \
    -subj "/CN=127.0.0.1" \
    -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" >/dev/null 2>&1
fi

echo "brav HTTPS: open https://${HOST}:${PORT}/"
exec "$PYTHON_BIN" -m uvicorn backend.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --ssl-keyfile "$KEY_FILE" \
  --ssl-certfile "$CERT_FILE" \
  --reload
