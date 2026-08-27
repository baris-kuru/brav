#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="python3"
if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi

echo "brav: open http://${CAFE_HOST:-127.0.0.1}:${CAFE_PORT:-8010}/"
exec "$PYTHON_BIN" -m uvicorn backend.app:app --host "${CAFE_HOST:-127.0.0.1}" --port "${CAFE_PORT:-8010}" --reload
