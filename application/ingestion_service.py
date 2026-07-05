"""
application/ingestion_service.py — Turns raw text into a LifeAdminItem.

SRP: this service has one job — parse raw input and store it in memory.
     It does NOT decide reminder timing (that is ReminderEngine's job).

The LLM-based parsing is isolated in `_parse_raw_text()` so it can be
tested in isolation and swapped without touching the rest of the service.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import date, datetime
from typing import Any

from domain.exceptions import IngestionError, MemoryOperationError
from domain.models import Category, ItemStatus, LifeAdminItem
from memory.port import MemoryPort

logger = logging.getLogger(__name__)


class IngestionService:
    """
    Parses raw text input → LifeAdminItem, then persists via MemoryPort.

    Constructor-injected MemoryPort (DIP): tests pass FakeMemoryPort,
    production passes LocalCogneeAdapter or CloudCogneeAdapter.
    """

    def __init__(self, memory_port: MemoryPort) -> None:
        self._memory = memory_port

    async def remember_item(
        self,
        raw_text: str,
        *,
        price: float | None = None,
        related_item_ids: list[str] | None = None,
    ) -> LifeAdminItem:
        """
        Parse `raw_text` into a structured LifeAdminItem and persist it.

        Args:
            raw_text: Free-form description — manual entry, pasted email, PDF text.
            related_item_ids: Optional explicit graph edges to other items.

        Returns:
            The fully-constructed LifeAdminItem that was stored.

        Raises:
            IngestionError: If parsing fails or memory write fails.
        """
        try:
            parsed = _parse_raw_text(raw_text)
        except Exception as exc:
            raise IngestionError(f"Failed to parse input: {exc}") from exc

        if not parsed.get("vendor"):
            parsed["vendor"] = parsed.get("name", "Unknown")
            
        price = price if price is not None else parsed.get("price")
        if isinstance(price, str) and price.startswith("."):
            logger.warning("Extracted price %s looks truncated (missing leading digit).", price)

        item = LifeAdminItem(
            item_id=parsed.get("item_id") or str(uuid.uuid4()),
            name=parsed["name"],
            category=Category(parsed["category"]),
            vendor=parsed["vendor"],
            key_date=_coerce_date(parsed["key_date"]),
            price=price,
            notes=parsed.get("notes", raw_text),
            status=ItemStatus.ACTIVE,
            related_item_ids=related_item_ids or [],
        )

        logger.info("remember item_id=%s category=%s", item.item_id, item.category)
        try:
            await self._memory.remember(item)
        except Exception as exc:
            raise IngestionError(f"Memory write failed: {exc}") from exc

        return item


# ---------------------------------------------------------------------------
# Parsing helpers — isolated so they're independently testable and replaceable
# ---------------------------------------------------------------------------

def _parse_raw_text(raw_text: str) -> dict[str, Any]:
    """
    Extract structured fields from free-form text.

    Strategy (in priority order):
    1. If an LLM API key is present → use the LLM prompt.
       Supports OpenAI directly or OpenRouter (set LLM_ENDPOINT + OPENROUTER_API_KEY).
    2. Otherwise → fall back to deterministic regex heuristics.

    This keeps the service testable without API keys: FakeMemoryPort tests
    use the regex path by default (no env vars set in CI).
    """
    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    if api_key:
        try:
            return _parse_with_llm(raw_text, api_key)
        except Exception:
            logger.warning("LLM parse failed, falling back to heuristics")

    return _parse_with_heuristics(raw_text)


def _parse_with_llm(raw_text: str, api_key: str) -> dict[str, Any]:
    """
    Call an LLM to extract structured fields from free text.

    Works with:
      - OpenAI directly (OPENAI_API_KEY set, no LLM_ENDPOINT)
      - OpenRouter      (OPENROUTER_API_KEY + LLM_ENDPOINT=https://openrouter.ai/api/v1)
      - Any OpenAI-compatible endpoint (LLM_API_KEY + LLM_ENDPOINT)
    """
    import openai  # only imported when API key is present

    endpoint = os.getenv("LLM_ENDPOINT")  # e.g. https://openrouter.ai/api/v1
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    client_kwargs: dict = {"api_key": api_key}
    if endpoint:
        client_kwargs["base_url"] = endpoint

    client = openai.OpenAI(**client_kwargs)
    system = (
        "You are a structured-data extractor. "
        "Extract the following fields from the user's text and return ONLY valid JSON:\n"
        "  name (str), vendor (str), category (one of: subscription, free_trial, "
        "warranty, insurance, domain_renewal, other), key_date (YYYY-MM-DD), "
        "price (float or null), notes (str).\n"
        "If a field is unclear, make a reasonable inference. Never add extra keys."
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": raw_text},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    content = response.choices[0].message.content
    if content is None:
        raise ValueError("LLM returned no content")
    return json.loads(content)


def _parse_with_heuristics(raw_text: str) -> dict[str, Any]:
    """
    Deterministic regex-based field extraction — no external dependencies.

    Used in tests (no API key) and as fallback when LLM is unavailable.
    """
    text_lower = raw_text.lower()

    # --- category ---
    category = "other"
    for cat in ("subscription", "free_trial", "warranty", "insurance", "domain_renewal"):
        if cat.replace("_", " ") in text_lower or cat in text_lower:
            category = cat
            break

    # --- key_date ---
    # Matches: 2025-08-15, Aug 15 2025, 15/08/2025, August 15, 2025
    date_patterns = [
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{1,2}/\d{1,2}/\d{4})\b",
        r"\b(\w+ \d{1,2},?\s*\d{4})\b",
    ]
    key_date_str = None
    for pat in date_patterns:
        m = re.search(pat, raw_text)
        if m:
            key_date_str = m.group(1)
            break
    if not key_date_str:
        key_date_str = date.today().isoformat()  # safe fallback

    # --- price ---
    price = None
    price_match = re.search(r"\$\s*([\d,]+\.?\d*)", raw_text)
    if price_match:
        price = float(price_match.group(1).replace(",", ""))

    # --- vendor / name ---
    # Heuristic: first quoted string or first two capitalized words
    quoted = re.findall(r'"([^"]+)"', raw_text)
    if quoted:
        name = quoted[0]
        vendor = quoted[1] if len(quoted) > 1 else quoted[0]
    else:
        words = raw_text.split()
        name = " ".join(words[:3]) if words else "Unknown"
        vendor = words[0] if words else "Unknown"

    return {
        "name": name,
        "vendor": vendor,
        "category": category,
        "key_date": key_date_str,
        "price": price,
        "notes": raw_text,
    }


def _coerce_date(value: Any) -> date:
    """Convert various date representations to a Python date object."""
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise IngestionError(f"Cannot parse date: {s!r}")
