from __future__ import annotations

import json
from typing import Any, TypeVar

import certifi
import httpx
from pydantic import BaseModel, ValidationError

from .config import FIREWORKS_API_KEY, FIREWORKS_MODEL

T = TypeVar("T", bound=BaseModel)
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"


def is_configured() -> bool:
  return bool(FIREWORKS_API_KEY)


def _headers() -> dict[str, str]:
  return {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {FIREWORKS_API_KEY}",
  }


def _messages(messages: list[dict[str, str]], system: str | None) -> list[dict[str, str]]:
  payload: list[dict[str, str]] = []
  if system:
    payload.append({"role": "system", "content": system})
  payload.extend(messages)
  return payload


def _extract_content(message: Any) -> str:
  content = getattr(message, "content", "")
  if isinstance(content, list):
    parts: list[str] = []
    for item in content:
      text = getattr(item, "text", None)
      if text:
        parts.append(str(text))
      elif isinstance(item, dict) and item.get("text"):
        parts.append(str(item["text"]))
    return "".join(parts).strip()
  return str(content).strip()


async def chat_once(
  messages: list[dict[str, str]],
  *,
  system: str | None = None,
  max_tokens: int = 1000,
  temperature: float = 0.1,
  response_format: dict[str, Any] | None = None,
) -> str:
  payload: dict[str, Any] = {
    "model": FIREWORKS_MODEL,
    "messages": _messages(messages, system),
    "stream": False,
    "max_tokens": max_tokens,
    "temperature": temperature,
  }
  if response_format is not None:
    payload["response_format"] = response_format

  async with httpx.AsyncClient(timeout=90, verify=certifi.where()) as client:
    response = await client.post(f"{FIREWORKS_BASE_URL}/chat/completions", headers=_headers(), json=payload)
    response.raise_for_status()
    data = response.json()
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content") or message.get("reasoning_content", "")
    if isinstance(content, list):
      return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict)).strip()
    return str(content).strip()


async def chat_structured(
  messages: list[dict[str, str]],
  schema: type[T],
  *,
  system: str | None = None,
  max_tokens: int = 1500,
  temperature: float = 0.1,
) -> T | None:
  schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
  raw = await chat_once(
    [
      *messages,
      {
        "role": "user",
        "content": (
          "Return a valid JSON object matching this schema exactly. "
          "Do not include commentary, markdown, or reasoning.\n\n"
          f"{schema_json}"
        ),
      },
    ],
    system=system,
    max_tokens=max_tokens,
    temperature=temperature,
    response_format={"type": "json_object"},
  )
  try:
    return schema.model_validate_json(raw)
  except (ValidationError, ValueError, json.JSONDecodeError):
    return None
