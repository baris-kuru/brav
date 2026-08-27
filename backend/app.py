from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .analytics import answer_manager_question, answer_question, build_dashboard_story, fetch_overview
from .config import STATIC_DIR, ensure_directories
from .db import get_conn, init_db
from .operations import fetch_operations_snapshot, seed_initial_operations
from .receipts import extract_pdf_pages, insert_receipt, pages_to_windows, save_upload, ai_extract_receipts
from .schemas import AskPayload, ManagerAskPayload

app = FastAPI(title="brav")
app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

ensure_directories()
init_db()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root() -> FileResponse:
  return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
  return {"status": "ok"}


@app.post("/api/receipts/ingest")
async def ingest_receipts(batch_name: str | None = Query(default=None), files: list[UploadFile] = File(...)) -> dict:
  pdfs = [item for item in files if item.filename and item.filename.lower().endswith(".pdf")]
  if not pdfs:
    raise HTTPException(status_code=400, detail="Upload at least one PDF file.")

  batch_title = batch_name or f"Cafe batch {datetime.now().strftime('%Y-%m-%d %H:%M')}"

  with get_conn() as conn:
    batch_cursor = conn.execute(
      "INSERT INTO batches (batch_name, file_count, status) VALUES (?, ?, 'processing')",
      (batch_title, len(pdfs)),
    )
    batch_id = int(batch_cursor.lastrowid)

  created_receipts = 0
  document_summaries: list[dict] = []

  for upload in pdfs:
    payload = await upload.read()
    stored_path = save_upload(batch_id, upload.filename or "upload.pdf", payload)

    with get_conn() as conn:
      document_cursor = conn.execute(
        """
        INSERT INTO documents (batch_id, filename, stored_path, status)
        VALUES (?, ?, ?, 'saved')
        """,
        (batch_id, upload.filename or stored_path.name, str(stored_path)),
      )
      document_id = int(document_cursor.lastrowid)

    pages = extract_pdf_pages(stored_path)
    page_text = "\n\n".join(f"--- Page {page.page_number} ---\n{page.text}" for page in pages)

    with get_conn() as conn:
      conn.execute(
        """
        UPDATE documents
        SET page_count = ?, extracted_text = ?, status = 'parsed'
        WHERE id = ?
        """,
        (len(pages), page_text, document_id),
      )

    receipt_buffers: list[tuple[object, str]] = []
    for window_text, page_numbers in pages_to_windows(pages):
      receipts = await ai_extract_receipts(window_text, page_numbers)
      receipt_buffers.extend((receipt, window_text) for receipt in receipts)

    with get_conn() as conn:
      for receipt, raw_text in receipt_buffers:
        insert_receipt(conn, batch_id, document_id, receipt, raw_text)
        created_receipts += 1
      conn.execute("UPDATE documents SET status = 'complete' WHERE id = ?", (document_id,))

    document_summaries.append(
      {
        "document_id": document_id,
        "filename": upload.filename,
        "pages": len(pages),
        "receipts_detected": len(receipt_buffers),
      }
    )

  with get_conn() as conn:
    conn.execute(
      "UPDATE batches SET receipt_count = ?, status = 'complete' WHERE id = ?",
      (created_receipts, batch_id),
    )

  return {
    "batch_id": batch_id,
    "batch_name": batch_title,
    "files_processed": len(pdfs),
    "receipts_detected": created_receipts,
    "documents": document_summaries,
  }


@app.get("/api/batches")
async def list_batches(limit: int = Query(default=12, le=50)) -> dict:
  with get_conn() as conn:
    rows = conn.execute(
      """
      SELECT id, batch_name, uploaded_at, file_count, receipt_count, status
      FROM batches
      ORDER BY id DESC
      LIMIT ?
      """,
      (limit,),
    ).fetchall()
  return {"batches": [dict(row) for row in rows]}


@app.get("/api/receipts")
async def list_receipts(limit: int = Query(default=50, le=200), merchant: str | None = None) -> dict:
  sql = """
    SELECT
      r.id,
      r.document_id,
      r.batch_id,
      COALESCE(r.merchant_name, 'Unknown') AS merchant_name,
      r.business_date,
      r.total,
      r.currency,
      r.confidence,
      d.filename
    FROM receipts r
    JOIN documents d ON d.id = r.document_id
  """
  params: list[object] = []
  if merchant:
    sql += " WHERE COALESCE(r.merchant_name, '') LIKE ? "
    params.append(f"%{merchant}%")
  sql += " ORDER BY COALESCE(r.business_date, r.created_at) DESC, r.id DESC LIMIT ?"
  params.append(limit)

  with get_conn() as conn:
    rows = conn.execute(sql, tuple(params)).fetchall()
  return {"receipts": [dict(row) for row in rows]}


@app.get("/api/dashboard")
async def dashboard() -> dict:
  with get_conn() as conn:
    overview = fetch_overview(conn)
    operations = fetch_operations_snapshot(conn)
  story = await build_dashboard_story(overview)
  return {"overview": overview, "operations": operations, "story": story}


async def seed_cafe_data_payload() -> dict:
  with get_conn() as conn:
    counts = seed_initial_operations(conn)
    operations = fetch_operations_snapshot(conn)
  return {"ok": True, "seeded": counts, "operations": operations}


@app.post("/api/data/seed")
async def seed_cafe_data() -> dict:
  return await seed_cafe_data_payload()


@app.get("/api/operations")
async def operations() -> dict:
  with get_conn() as conn:
    return fetch_operations_snapshot(conn)


@app.post("/api/analysis/ask")
async def ask_analysis(payload: AskPayload) -> dict:
  with get_conn() as conn:
    overview = fetch_overview(conn)
    receipts = [
      dict(row)
      for row in conn.execute(
        """
        SELECT COALESCE(merchant_name, 'Unknown') AS merchant_name, business_date, total, summary, confidence
        FROM receipts
        ORDER BY id DESC
        LIMIT 20
        """
      ).fetchall()
    ]
    answer = await answer_question(payload.question, overview, receipts)
    conn.execute(
      "INSERT INTO analysis_runs (analysis_type, prompt, content) VALUES (?, ?, ?)",
      ("question", payload.question, answer),
    )
  return {"answer": answer}


@app.post("/api/manager/ask")
async def ask_manager(payload: ManagerAskPayload) -> dict:
  with get_conn() as conn:
    overview = fetch_overview(conn)
    operations = fetch_operations_snapshot(conn)
    answer = await answer_manager_question(payload.question, overview, operations)
    conn.execute(
      "INSERT INTO analysis_runs (analysis_type, prompt, content) VALUES (?, ?, ?)",
      ("manager_twin", payload.question, answer),
    )
  return {"answer": answer}


@app.get("/api/merchants/{merchant_name}")
async def merchant_detail(merchant_name: str) -> dict:
  with get_conn() as conn:
    rows = conn.execute(
      """
      SELECT id, business_date, total, currency, summary, confidence
      FROM receipts
      WHERE COALESCE(merchant_name, 'Unknown') = ?
      ORDER BY COALESCE(business_date, created_at) DESC
      LIMIT 100
      """,
      (merchant_name,),
    ).fetchall()
  return {"merchant": merchant_name, "receipts": [dict(row) for row in rows]}
