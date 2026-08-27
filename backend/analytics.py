from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any

from .fireworks import chat_structured, is_configured
from .schemas import AnalysisAnswerResponse, DashboardInsightResponse


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
  return [dict(row) for row in rows]


def fetch_overview(conn: sqlite3.Connection) -> dict[str, Any]:
  totals = conn.execute(
    """
    SELECT
      COUNT(*) AS receipt_count,
      COUNT(DISTINCT merchant_name) AS merchant_count,
      COALESCE(SUM(total), 0) AS total_spend,
      COALESCE(AVG(total), 0) AS avg_ticket
    FROM receipts
    """
  ).fetchone()

  merchant_breakdown = rows_to_dicts(
    conn.execute(
      """
      SELECT COALESCE(merchant_name, 'Unknown') AS label, COUNT(*) AS visits, COALESCE(SUM(total), 0) AS spend
      FROM receipts
      GROUP BY COALESCE(merchant_name, 'Unknown')
      ORDER BY spend DESC, visits DESC
      LIMIT 8
      """
    ).fetchall()
  )

  daily_spend = rows_to_dicts(
    conn.execute(
      """
      SELECT COALESCE(business_date, substr(created_at, 1, 10)) AS label, COALESCE(SUM(total), 0) AS spend
      FROM receipts
      GROUP BY COALESCE(business_date, substr(created_at, 1, 10))
      ORDER BY label DESC
      LIMIT 14
      """
    ).fetchall()
  )[::-1]

  category_breakdown = rows_to_dicts(
    conn.execute(
      """
      SELECT COALESCE(category, 'Uncategorized') AS label, COUNT(*) AS lines, COALESCE(SUM(total_price), 0) AS spend
      FROM receipt_items
      GROUP BY COALESCE(category, 'Uncategorized')
      ORDER BY spend DESC, lines DESC
      LIMIT 8
      """
    ).fetchall()
  )

  recent_receipts = rows_to_dicts(
    conn.execute(
      """
      SELECT id, COALESCE(merchant_name, 'Unknown') AS merchant_name, business_date, total, confidence
      FROM receipts
      ORDER BY COALESCE(business_date, created_at) DESC, id DESC
      LIMIT 12
      """
    ).fetchall()
  )

  return {
    "totals": dict(totals) if totals else {
      "receipt_count": 0,
      "merchant_count": 0,
      "total_spend": 0,
      "avg_ticket": 0,
    },
    "merchant_breakdown": merchant_breakdown,
    "daily_spend": daily_spend,
    "category_breakdown": category_breakdown,
    "recent_receipts": recent_receipts,
  }


async def build_dashboard_story(overview: dict[str, Any]) -> str:
  if not overview["totals"]["receipt_count"]:
    return "Upload a batch of receipt PDFs to generate the first cafe operations dashboard."

  if not is_configured():
    top_merchant = overview["merchant_breakdown"][0]["label"] if overview["merchant_breakdown"] else "Unknown"
    total_spend = overview["totals"]["total_spend"]
    avg_ticket = overview["totals"]["avg_ticket"]
    return (
      f"Current data shows {overview['totals']['receipt_count']} receipts across "
      f"{overview['totals']['merchant_count']} merchants. Total tracked spend is {total_spend:.2f}, "
      f"average ticket is {avg_ticket:.2f}, and the heaviest merchant so far is {top_merchant}."
    )

  prompt = (
    "You are a cafe operations analyst. Review the aggregated receipt dataset and write "
    "a short management insight paragraph plus three crisp action bullets. Focus on spend, "
    "merchant concentration, unusual trends, and data quality caveats. Do not include any "
    "thinking, preamble, or hidden reasoning.\n\n"
    f"{json.dumps(overview, ensure_ascii=False)}"
  )
  answer = await chat_structured(
    [{"role": "user", "content": prompt}],
    DashboardInsightResponse,
    system="Return only the final management insight payload.",
    max_tokens=500,
    temperature=0.15,
  )
  if answer:
    action_lines = "\n".join(f"- {item}" for item in answer.actions[:3])
    return f"{answer.summary.strip()}\n\n{action_lines}".strip()
  top_merchant = overview["merchant_breakdown"][0]["label"] if overview["merchant_breakdown"] else "Unknown"
  return (
    f"Tracked spend is {overview['totals']['total_spend']:.2f} across "
    f"{overview['totals']['receipt_count']} receipts, with an average ticket of "
    f"{overview['totals']['avg_ticket']:.2f}. Right now the data is concentrated in "
    f"{top_merchant}, so the dashboard should be treated as an early signal rather than a trend line.\n\n"
    "- Upload more batches to improve confidence and merchant coverage.\n"
    "- Review low-confidence receipts before using the totals for reporting.\n"
    "- Add item categories over time to unlock product-mix analysis."
  )


async def answer_question(question: str, overview: dict[str, Any], receipts: list[dict[str, Any]]) -> str:
  if not receipts:
    return "There are no receipts in the database yet."

  if not is_configured():
    return (
      "AI analysis is not configured yet, but the database is available. "
      f"Current totals: {overview['totals']['receipt_count']} receipts and "
      f"{overview['totals']['total_spend']:.2f} total spend."
    )

  context = {
    "overview": overview,
    "recent_receipts": receipts[:15],
  }
  structured = await chat_structured(
    [{"role": "user", "content": f"Question: {question}\n\nData:\n{json.dumps(context, ensure_ascii=False)}"}],
    AnalysisAnswerResponse,
    system=(
      "Answer as a cafe management analyst using only the provided data. "
      "Do not reveal chain-of-thought. If uncertain, say what is missing."
    ),
    max_tokens=500,
    temperature=0.1,
  )
  if structured:
    return structured.answer.strip()
  top_merchant = overview["merchant_breakdown"][0]["label"] if overview["merchant_breakdown"] else "Unknown"
  return (
    f"Current data is still sparse: {overview['totals']['receipt_count']} receipts, "
    f"{overview['totals']['total_spend']:.2f} total spend, average ticket "
    f"{overview['totals']['avg_ticket']:.2f}, and top merchant {top_merchant}. "
    "There is also at least one extraction-quality issue in the dataset, so I would "
    "treat any trend answer as provisional until more batches are ingested."
  )


async def answer_manager_question(question: str, overview: dict[str, Any], operations: dict[str, Any]) -> str:
  context = {
    "receipt_overview": overview,
    "operations": operations,
  }
  if is_configured():
    try:
      structured = await asyncio.wait_for(
        chat_structured(
          [{"role": "user", "content": f"Question: {question}\n\nCafe state:\n{json.dumps(context, ensure_ascii=False)}"}],
          AnalysisAnswerResponse,
          system=(
            "You are the digital twin of a practical cafe manager. Use only the provided cafe state. "
            "Answer with concise, concrete actions across stock, staffing, prep, weather, daypart, and receipts. "
            "Do not include hidden reasoning."
          ),
          max_tokens=650,
          temperature=0.15,
        ),
        timeout=8,
      )
    except TimeoutError:
      structured = None
    if structured:
      return structured.answer.strip()

  priorities = operations.get("priorities", [])[:3]
  staffing = operations.get("staffing", [])
  summary = operations.get("summary", {})
  afternoon = [row for row in staffing if str(row.get("daypart", "")).startswith(("11:", "14:", "17:"))]
  staffing_text = "; ".join(
    f"{row['daypart']}: keep {row['scheduled_staff']} scheduled for {row['expected_orders']} expected orders"
    for row in afternoon[:3]
  )
  priority_text = "; ".join(item["title"] for item in priorities) if priorities else "no open priorities"
  return (
    f"Manager read: expected orders are {summary.get('expected_orders', 0)}, peak recommended staffing is "
    f"{summary.get('recommended_staff_peak', 0)}, and the current staffing gap is "
    f"{summary.get('staffing_gap', 0)}. Stock watch count is {summary.get('low_stock_count', 0)}. "
    f"For staffing: {staffing_text or 'no staffing forecast loaded'}. "
    f"Top actions: {priority_text}."
  )
