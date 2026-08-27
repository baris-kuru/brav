from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any


INITIAL_STOCK = [
  ("Espresso beans", "kg", 18.5, 6.0, 8.2, "Caffe Roma", "2026-06-20", "ok"),
  ("Oat milk", "liters", 22.0, 14.0, 18.5, "Green Dairy", "2026-06-19", "watch"),
  ("Whole milk", "liters", 36.0, 20.0, 26.0, "Green Dairy", "2026-06-19", "ok"),
  ("Croissants", "pieces", 28.0, 30.0, 42.0, "Bakery North", "2026-06-19", "reorder"),
  ("Eggs", "pieces", 90.0, 48.0, 52.0, "Farmline", "2026-06-20", "ok"),
  ("Avocado", "pieces", 16.0, 18.0, 24.0, "Fresh Market", "2026-06-19", "reorder"),
  ("Takeaway cups 12oz", "pieces", 190.0, 120.0, 145.0, "PackPro", "2026-06-21", "ok"),
]

INITIAL_FORECASTS = [
  ("08:00-11:00", 18, "rain", 0, 0, 78, 4, 5, "Rain should pull more takeaway coffee demand into the morning rush."),
  ("11:00-14:00", 21, "cloudy", 0, 0, 64, 3, 4, "Lunch will be steady but not peak; keep one flex person callable."),
  ("14:00-17:00", 23, "sunny", 0, 0, 54, 2, 3, "Terrace demand should lift after 14:00 if the rain clears."),
  ("17:00-20:00", 20, "clear", 0, 0, 36, 2, 2, "Late day can run lean unless events nearby change footfall."),
]

INITIAL_PRIORITIES = [
  ("critical", "Restock croissants before 10:30", "Stock is below the morning threshold while demand forecast is high.", "inventory"),
  ("high", "Schedule one extra morning floor person", "Rain plus weekday commute pattern points to a heavier 08:00-11:00 spike.", "staffing"),
  ("medium", "Prep avocado toast components before lunch", "Avocado is below par and lunch forecast still needs menu coverage.", "prep"),
  ("medium", "Check takeaway cup count after morning rush", "Current level is healthy but weather may shift orders to takeaway.", "inventory"),
]

INITIAL_EVENTS = [
  ("2026-06-19", "Friday", 0, 0, "Normal weekday with rain in the morning and clearer afternoon weather."),
  ("2026-06-20", "Saturday", 1, 0, "Weekend pattern: brunch demand higher, fewer office commuters."),
  ("2026-06-21", "Sunday", 1, 0, "Weekend pattern: slower start, longer late brunch tail."),
]


def ensure_operations_schema(conn: sqlite3.Connection) -> None:
  conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS stock_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      item_name TEXT NOT NULL UNIQUE,
      unit TEXT NOT NULL,
      current_qty REAL NOT NULL,
      reorder_point REAL NOT NULL,
      expected_daily_usage REAL NOT NULL,
      supplier TEXT,
      next_delivery_date TEXT,
      status TEXT NOT NULL DEFAULT 'ok',
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS staffing_forecasts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      daypart TEXT NOT NULL,
      temperature_c REAL,
      weather TEXT,
      is_weekend INTEGER NOT NULL DEFAULT 0,
      is_holiday INTEGER NOT NULL DEFAULT 0,
      expected_orders INTEGER NOT NULL,
      recommended_staff INTEGER NOT NULL,
      scheduled_staff INTEGER NOT NULL,
      rationale TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS manager_priorities (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      severity TEXT NOT NULL,
      title TEXT NOT NULL,
      rationale TEXT NOT NULL,
      category TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS cafe_calendar_signals (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      business_date TEXT NOT NULL UNIQUE,
      day_name TEXT NOT NULL,
      is_weekend INTEGER NOT NULL DEFAULT 0,
      is_holiday INTEGER NOT NULL DEFAULT 0,
      note TEXT NOT NULL
    );
    """
  )


def seed_initial_operations(conn: sqlite3.Connection) -> dict[str, int]:
  ensure_operations_schema(conn)
  conn.execute("DELETE FROM stock_items")
  conn.execute("DELETE FROM staffing_forecasts")
  conn.execute("DELETE FROM manager_priorities")
  conn.execute("DELETE FROM cafe_calendar_signals")

  conn.executemany(
    """
    INSERT INTO stock_items (
      item_name, unit, current_qty, reorder_point, expected_daily_usage,
      supplier, next_delivery_date, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
    INITIAL_STOCK,
  )
  conn.executemany(
    """
    INSERT INTO staffing_forecasts (
      daypart, temperature_c, weather, is_weekend, is_holiday,
      expected_orders, recommended_staff, scheduled_staff, rationale
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    INITIAL_FORECASTS,
  )
  conn.executemany(
    """
    INSERT INTO manager_priorities (severity, title, rationale, category)
    VALUES (?, ?, ?, ?)
    """,
    INITIAL_PRIORITIES,
  )
  conn.executemany(
    """
    INSERT INTO cafe_calendar_signals (business_date, day_name, is_weekend, is_holiday, note)
    VALUES (?, ?, ?, ?, ?)
    """,
    INITIAL_EVENTS,
  )
  return {
    "stock_items": len(INITIAL_STOCK),
    "staffing_forecasts": len(INITIAL_FORECASTS),
    "manager_priorities": len(INITIAL_PRIORITIES),
    "calendar_signals": len(INITIAL_EVENTS),
  }


def fetch_operations_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
  ensure_operations_schema(conn)
  stock = [dict(row) for row in conn.execute(
    """
    SELECT *, ROUND(current_qty / NULLIF(expected_daily_usage, 0), 1) AS days_left
    FROM stock_items
    ORDER BY
      CASE status WHEN 'reorder' THEN 0 WHEN 'watch' THEN 1 ELSE 2 END,
      days_left ASC
    """
  ).fetchall()]
  forecasts = [dict(row) for row in conn.execute(
    """
    SELECT *
    FROM staffing_forecasts
    ORDER BY id ASC
    """
  ).fetchall()]
  priorities = [dict(row) for row in conn.execute(
    """
    SELECT *
    FROM manager_priorities
    WHERE status = 'open'
    ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, id ASC
    """
  ).fetchall()]
  calendar = [dict(row) for row in conn.execute(
    """
    SELECT *
    FROM cafe_calendar_signals
    ORDER BY business_date ASC
    """
  ).fetchall()]

  low_stock_count = sum(1 for item in stock if item["status"] in {"reorder", "watch"})
  staffing_gap = sum(max(0, row["recommended_staff"] - row["scheduled_staff"]) for row in forecasts)
  expected_orders = sum(row["expected_orders"] for row in forecasts)
  recommended_staff_peak = max([row["recommended_staff"] for row in forecasts] or [0])

  return {
    "as_of": datetime.now().isoformat(timespec="minutes"),
    "summary": {
      "low_stock_count": low_stock_count,
      "staffing_gap": staffing_gap,
      "expected_orders": expected_orders,
      "recommended_staff_peak": recommended_staff_peak,
    },
    "stock": stock,
    "staffing": forecasts,
    "priorities": priorities,
    "calendar": calendar,
  }
