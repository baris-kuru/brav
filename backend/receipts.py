from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import httpx
from pypdf import PdfReader

from .config import DOCLING_URL, UPLOADS_DIR
from .fireworks import chat_structured, is_configured
from .schemas import ExtractedReceipt, ReceiptExtractionResponse, ReceiptItem

TOTAL_PATTERNS = [
  re.compile(r"(?im)^(?:grand\s+)?total[:\s]*([0-9]+(?:[.,][0-9]{2})?)\b"),
  re.compile(r"(?im)^toplam[:\s]*([0-9]+(?:[.,][0-9]{2})?)\b"),
]
SUBTOTAL_PATTERNS = [
  re.compile(r"(?im)^subtotal[:\s]*([0-9]+(?:[.,][0-9]{2})?)\b"),
  re.compile(r"(?im)^ara\s+toplam[:\s]*([0-9]+(?:[.,][0-9]{2})?)\b"),
]
DATE_PATTERNS = [
  re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
  re.compile(r"\b(\d{2}[./-]\d{2}[./-]\d{4})\b"),
]
TIME_PATTERN = re.compile(r"\b(\d{2}:\d{2}(?::\d{2})?)\b")
PRICE_LINE_PATTERN = re.compile(r"^(?P<name>.+?)\s{2,}(?P<price>\d+(?:[.,]\d{2})?)$")


@dataclass
class PageText:
  page_number: int
  text: str


def normalize_text(text: str) -> str:
  text = text.replace("\x00", " ").replace("\r", "\n")
  lines = [re.sub(r"\s+", " ", raw).strip() for raw in text.splitlines()]
  compacted: list[str] = []
  blank_streak = 0
  for line in lines:
    if not line:
      blank_streak += 1
      if blank_streak <= 1:
        compacted.append("")
      continue
    blank_streak = 0
    compacted.append(line)
  return "\n".join(compacted).strip()


def extract_pdf_pages(pdf_path: Path) -> list[PageText]:
  reader = PdfReader(str(pdf_path))
  pages: list[PageText] = []
  for index, page in enumerate(reader.pages, start=1):
    text = normalize_text(page.extract_text() or "")
    pages.append(PageText(page_number=index, text=text))
  if sum(len(page.text) for page in pages) < 40:
    fallback = extract_with_docling(pdf_path)
    if fallback:
      return fallback
  return pages


def extract_with_docling(pdf_path: Path) -> list[PageText]:
  try:
    with pdf_path.open("rb") as handle:
      response = httpx.post(
        DOCLING_URL,
        files={"file": (pdf_path.name, handle, "application/pdf")},
        timeout=120,
      )
    if not response.is_success:
      return []
    payload = response.json()
    markdown = normalize_text(str(payload.get("markdown", "")))
    if not markdown:
      return []
    return [PageText(page_number=1, text=markdown)]
  except Exception:
    return []


def pages_to_windows(pages: Iterable[PageText], max_chars: int = 14000) -> list[tuple[str, list[int]]]:
  windows: list[tuple[str, list[int]]] = []
  for page in pages:
    page_block = f"--- Page {page.page_number} ---\n{page.text or '[empty page]'}\n"
    if len(page_block) > max_chars:
      chunks = [
        page_block[index:index + max_chars]
        for index in range(0, len(page_block), max_chars)
      ]
      windows.extend((chunk, [page.page_number]) for chunk in chunks if chunk.strip())
      continue
    windows.append((page_block, [page.page_number]))
  return windows


def _parse_amount(patterns: list[re.Pattern[str]], text: str) -> float | None:
  for pattern in patterns:
    match = pattern.search(text)
    if match:
      value = match.group(1).replace(",", ".")
      try:
        return float(value)
      except ValueError:
        return None
  return None


def _parse_date(text: str) -> str | None:
  for pattern in DATE_PATTERNS:
    match = pattern.search(text)
    if not match:
      continue
    candidate = match.group(1)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
      try:
        return datetime.strptime(candidate, fmt).date().isoformat()
      except ValueError:
        continue
  return None


def _parse_time(text: str) -> str | None:
  match = TIME_PATTERN.search(text)
  return match.group(1) if match else None


def _guess_merchant(text: str) -> str | None:
  for line in text.splitlines():
    stripped = line.strip(" -:")
    if len(stripped) < 3:
      continue
    lowered = stripped.lower()
    if lowered.startswith("page ") or lowered.startswith("--- page"):
      continue
    if any(token in lowered for token in ["total", "subtotal", "tax", "kdv", "cash", "visa", "mastercard"]):
      continue
    return stripped[:120]
  return None


def heuristic_items(text: str) -> list[ReceiptItem]:
  items: list[ReceiptItem] = []
  for line in text.splitlines():
    match = PRICE_LINE_PATTERN.match(line.strip())
    if not match:
      continue
    name = match.group("name").strip(" .:-")
    if len(name) < 2:
      continue
    price = float(match.group("price").replace(",", "."))
    items.append(ReceiptItem(name=name[:120], total_price=price))
  return items[:15]


def heuristic_receipt(text: str, page_numbers: list[int]) -> ExtractedReceipt:
  total = _parse_amount(TOTAL_PATTERNS, text)
  subtotal = _parse_amount(SUBTOTAL_PATTERNS, text)
  return ExtractedReceipt(
    merchant_name=_guess_merchant(text),
    business_date=_parse_date(text),
    business_time=_parse_time(text),
    currency="TRY" if "tl" in text.lower() or "kdv" in text.lower() else None,
    subtotal=subtotal,
    total=total,
    page_numbers=page_numbers,
    summary="Heuristic extraction fallback",
    confidence=0.35 if total is not None else 0.2,
    evidence_excerpt=text[:400],
    items=heuristic_items(text),
  )


async def ai_extract_receipts(window_text: str, page_numbers: list[int]) -> list[ExtractedReceipt]:
  if len(window_text.strip()) < 10:
    return []
  if not is_configured():
    return [heuristic_receipt(window_text, page_numbers)]

  system = (
    "You extract structured cafe receipts from OCR or PDF text. "
    "A single input can contain zero, one, or multiple receipts. "
    "Return only receipts that have evidence in the text. "
    "Leave uncertain fields null, keep confidence realistic, and never invent items."
  )
  user_prompt = (
    "Extract every distinct cafe receipt in this text window.\n"
    "If multiple receipts exist, return one object per receipt.\n"
    "Use ISO date YYYY-MM-DD when possible. Keep page numbers within the provided range.\n\n"
    f"Page range: {page_numbers}\n\n"
    f"{window_text}"
  )
  response = await chat_structured(
    [{"role": "user", "content": user_prompt}],
    ReceiptExtractionResponse,
    system=system,
    max_tokens=2200,
    temperature=0.05,
  )
  if not response or not response.receipts:
    return [heuristic_receipt(window_text, page_numbers)]

  normalized: list[ExtractedReceipt] = []
  for receipt in response.receipts:
    heuristic = heuristic_receipt(window_text, page_numbers)
    if receipt.total is None and heuristic.total is not None:
      receipt.total = heuristic.total
    if receipt.subtotal is None and heuristic.subtotal is not None:
      receipt.subtotal = heuristic.subtotal
    if not receipt.business_date and heuristic.business_date:
      receipt.business_date = heuristic.business_date
    if not receipt.business_time and heuristic.business_time:
      receipt.business_time = heuristic.business_time
    if not receipt.merchant_name and heuristic.merchant_name:
      receipt.merchant_name = heuristic.merchant_name
    if not receipt.items and heuristic.items:
      receipt.items = heuristic.items
    if not receipt.summary:
      receipt.summary = heuristic.summary
    if not receipt.page_numbers:
      receipt.page_numbers = page_numbers
    if not receipt.evidence_excerpt:
      receipt.evidence_excerpt = window_text[:400]
    normalized.append(receipt)
  return normalized


def save_upload(batch_id: int, filename: str, payload: bytes) -> Path:
  safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", filename).strip("-") or "upload.pdf"
  destination_dir = UPLOADS_DIR / f"batch-{batch_id}"
  destination_dir.mkdir(parents=True, exist_ok=True)
  destination = destination_dir / safe_name
  destination.write_bytes(payload)
  return destination


def insert_receipt(conn: sqlite3.Connection, batch_id: int, document_id: int, receipt: ExtractedReceipt, raw_text: str) -> int:
  cursor = conn.execute(
    """
    INSERT INTO receipts (
      batch_id, document_id, window_label, merchant_name, business_date, business_time,
      currency, subtotal, tax, tip, total, payment_method, receipt_number,
      page_numbers, summary, confidence, evidence_excerpt, raw_text, raw_payload
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
      batch_id,
      document_id,
      f"pages {receipt.page_numbers}",
      receipt.merchant_name,
      receipt.business_date,
      receipt.business_time,
      receipt.currency,
      receipt.subtotal,
      receipt.tax,
      receipt.tip,
      receipt.total,
      receipt.payment_method,
      receipt.receipt_number,
      json.dumps(receipt.page_numbers),
      receipt.summary,
      receipt.confidence,
      receipt.evidence_excerpt,
      raw_text,
      receipt.model_dump_json(),
    ),
  )
  receipt_id = int(cursor.lastrowid)
  for item in receipt.items:
    conn.execute(
      """
      INSERT INTO receipt_items (receipt_id, item_name, quantity, unit_price, total_price, category)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (receipt_id, item.name, item.quantity, item.unit_price, item.total_price, item.category),
    )
  return receipt_id
