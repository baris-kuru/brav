from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
DATA_DIR = Path(os.getenv("CAFE_DATA_DIR", ROOT_DIR / "data")).resolve()
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = Path(os.getenv("CAFE_DB_PATH", DATA_DIR / "cafe_ops.db")).resolve()

DEFAULT_FIREWORKS_MODEL = "accounts/fireworks/models/qwen3p6-plus"
DEFAULT_BACKEND_HOST = os.getenv("CAFE_HOST", "127.0.0.1")
DEFAULT_BACKEND_PORT = int(os.getenv("CAFE_PORT", "8010"))
DOCLING_URL = os.getenv("DOCLING_URL", "http://127.0.0.1:8183/convert")


def _load_env_file(path: Path) -> dict[str, str]:
  if not path.exists():
    return {}
  return {k: v for k, v in dotenv_values(path).items() if isinstance(v, str)}


def load_known_env() -> dict[str, str]:
  values: dict[str, str] = {}
  home_assistant_env = ROOT_DIR.parent / "HomeAssistant" / ".env"
  for candidate in [home_assistant_env, ROOT_DIR / ".env"]:
    values.update(_load_env_file(candidate))
  return values


KNOWN_ENV = load_known_env()
FIREWORKS_API_KEY = (os.getenv("FIREWORKS_API_KEY") or KNOWN_ENV.get("FIREWORKS_API_KEY") or "").strip()
FIREWORKS_MODEL = (os.getenv("FIREWORKS_MODEL") or KNOWN_ENV.get("FIREWORKS_MODEL") or DEFAULT_FIREWORKS_MODEL).strip()


def ensure_directories() -> None:
  for path in [DATA_DIR, UPLOADS_DIR]:
    path.mkdir(parents=True, exist_ok=True)
