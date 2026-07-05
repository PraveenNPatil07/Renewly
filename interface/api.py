"""
interface/api.py — FastAPI REST layer.

Thin routes — zero business logic. Each endpoint:
1. Parses the request
2. Calls the appropriate application service
3. Returns the result

The payoff of the layered architecture: these routes call the exact same
services as the CLI, proving the interface layer is genuine plumbing.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

# Load .env before anything else so all env vars are available
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config import get_memory_adapter
from application.cleanup_service import CleanupService
from application.feedback_service import FeedbackService
from application.ingestion_service import IngestionService
from application.query_service import QueryService
from domain.exceptions import (
    CleanupError,
    FeedbackError,
    IngestionError,
    ItemNotFoundError,
    QueryError,
)
from domain.models import Category, ItemStatus, LifeAdminItem
from scheduler.digest_job import run_digest_once

app = FastAPI(
    title="Renewly API",
    description=(
        "Life-Admin Memory Agent powered by Cognee. "
        "Switch between local and cloud backends via RENEWLY_BACKEND env var."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Shared service construction (singleton-per-request is fine for hackathon)
# ---------------------------------------------------------------------------

def _services():
    memory = get_memory_adapter()
    return (
        IngestionService(memory),
        QueryService(memory),
        FeedbackService(memory),
        CleanupService(memory),
        memory,
    )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AddRequest(BaseModel):
    raw_text: str
    related_item_ids: list[str] = []


class AddResponse(BaseModel):
    item_id: str
    name: str
    category: str
    vendor: str
    key_date: str
    price: Optional[float]
    status: str
    related_item_ids: list[str]


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


class FeedbackRequest(BaseModel):
    item_id: str
    signal: str  # too_early | too_late | just_right


class CleanupResponse(BaseModel):
    pruned_ids: list[str]
    count: int


class DigestResponse(BaseModel):
    digest: str


class ListItemResponse(BaseModel):
    item_id: str
    name: str
    category: str
    vendor: str
    key_date: str
    price: Optional[float]
    status: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Health check — also shows active backend."""
    import os
    return {"status": "ok", "backend": os.getenv("RENEWLY_BACKEND", "local")}


@app.post("/items", response_model=AddResponse, status_code=201)
async def add_item(req: AddRequest):
    """Ingest a new life-admin item from raw text."""
    ingestor, _, _, _, _ = _services()
    try:
        item = await ingestor.remember_item(
            req.raw_text, related_item_ids=req.related_item_ids
        )
    except IngestionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return AddResponse(
        item_id=item.item_id,
        name=item.name,
        category=item.category.value,
        vendor=item.vendor,
        key_date=item.key_date.isoformat(),
        price=item.price,
        status=item.status.value,
        related_item_ids=item.related_item_ids,
    )


@app.post("/query", response_model=AskResponse)
async def query(req: AskRequest):
    """Ask a natural-language question about your life-admin items."""
    _, query_svc, _, _, _ = _services()
    try:
        answer = await query_svc.ask(req.question)
    except QueryError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return AskResponse(answer=answer)


@app.post("/feedback", status_code=204)
async def feedback(req: FeedbackRequest):
    """Record user feedback to improve reminder timing."""
    _, _, feedback_svc, _, _ = _services()
    try:
        await feedback_svc.record_feedback(req.item_id, req.signal)
    except FeedbackError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/cleanup", response_model=CleanupResponse)
async def cleanup():
    """Prune stale/handled items from memory."""
    _, _, _, cleanup_svc, memory = _services()
    try:
        raw_results = await memory.list_all_items()
    except Exception:
        raw_results = []

    items = []
    for r in raw_results:
        try:
            item = LifeAdminItem(
                item_id=r.get("item_id", "unknown"),
                name=r.get("name", ""),
                category=Category(r.get("category", "other")),
                vendor=r.get("vendor", ""),
                key_date=date.fromisoformat(r["key_date"]),
                price=r.get("price"),
                notes=r.get("notes", ""),
                status=ItemStatus(r.get("status", "active")),
                related_item_ids=r.get("related_item_ids", []),
            )
            items.append(item)
        except Exception:
            continue

    try:
        pruned = await cleanup_svc.run_cleanup(items)
    except CleanupError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return CleanupResponse(pruned_ids=pruned, count=len(pruned))


@app.get("/digest", response_model=DigestResponse)
async def digest():
    """Get a reminder digest of items expiring soon."""
    _, query_svc, _, _, _ = _services()
    result = await run_digest_once(query_svc, print_output=False)
    return DigestResponse(digest=result)


@app.get("/list", response_model=list[ListItemResponse])
async def list_items():
    """Return all stored items, deduplicated through _normalise_results."""
    _, _, _, _, memory = _services()
    try:
        raw = await memory.list_all_items()
    except Exception:
        raw = []

    result = []
    for r in raw:
        try:
            result.append(ListItemResponse(
                item_id=r.get("item_id", ""),
                name=r.get("name", ""),
                category=r.get("category", "other"),
                vendor=r.get("vendor", ""),
                key_date=r.get("key_date", ""),
                price=r.get("price"),
                status=r.get("status", "active"),
                notes=r.get("notes", ""),
            ))
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# Static file serving — registered LAST so every API route above takes priority
# ---------------------------------------------------------------------------
import os as _os
from fastapi.staticfiles import StaticFiles as _StaticFiles

_frontend_path = _os.path.normpath(
    _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "frontend")
)
if _os.path.isdir(_frontend_path):
    app.mount("/", _StaticFiles(directory=_frontend_path, html=True), name="static")
