from __future__ import annotations

from pydantic import BaseModel, Field


class ReceiptItem(BaseModel):
  name: str
  quantity: float | None = None
  unit_price: float | None = None
  total_price: float | None = None
  category: str | None = None


class ExtractedReceipt(BaseModel):
  merchant_name: str | None = None
  business_date: str | None = None
  business_time: str | None = None
  currency: str | None = None
  subtotal: float | None = None
  tax: float | None = None
  tip: float | None = None
  total: float | None = None
  payment_method: str | None = None
  receipt_number: str | None = None
  page_numbers: list[int] = Field(default_factory=list)
  summary: str | None = None
  confidence: float = 0.0
  evidence_excerpt: str | None = None
  items: list[ReceiptItem] = Field(default_factory=list)


class ReceiptExtractionResponse(BaseModel):
  receipts: list[ExtractedReceipt] = Field(default_factory=list)


class AskPayload(BaseModel):
  question: str


class ManagerAskPayload(BaseModel):
  question: str
  mode: str = "manager"


class DashboardInsightResponse(BaseModel):
  summary: str
  actions: list[str] = Field(default_factory=list)


class AnalysisAnswerResponse(BaseModel):
  answer: str
