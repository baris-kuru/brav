from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .config import DB_PATH, ensure_directories


SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_name TEXT NOT NULL,
  uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  file_count INTEGER NOT NULL DEFAULT 0,
  receipt_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'processing',
  notes TEXT
);

CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  page_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  extracted_text TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  window_label TEXT,
  merchant_name TEXT,
  business_date TEXT,
  business_time TEXT,
  currency TEXT,
  subtotal REAL,
  tax REAL,
  tip REAL,
  total REAL,
  payment_method TEXT,
  receipt_number TEXT,
  page_numbers TEXT NOT NULL DEFAULT '[]',
  summary TEXT,
  confidence REAL NOT NULL DEFAULT 0,
  evidence_excerpt TEXT,
  raw_text TEXT NOT NULL DEFAULT '',
  raw_payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipt_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
  item_name TEXT NOT NULL,
  quantity REAL,
  unit_price REAL,
  total_price REAL,
  category TEXT
);

CREATE TABLE IF NOT EXISTS analysis_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  analysis_type TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect() -> sqlite3.Connection:
  ensure_directories()
  conn = sqlite3.connect(DB_PATH, timeout=30)
  conn.row_factory = sqlite3.Row
  return conn


@contextmanager
def get_conn() -> sqlite3.Connection:
  conn = connect()
  try:
    yield conn
    conn.commit()
  finally:
    conn.close()


def init_db() -> None:
  with get_conn() as conn:
    conn.executescript(SCHEMA)
    from .operations import ensure_operations_schema

    ensure_operations_schema(conn)
