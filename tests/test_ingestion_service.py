"""
tests/test_ingestion_service.py — Unit tests for IngestionService.

All tests use FakeMemoryPort — zero Cognee calls, zero LLM calls, sub-second.
This is the empirical proof that business logic is decoupled from Cognee.
"""

from __future__ import annotations

from datetime import date

import pytest

from application.ingestion_service import IngestionService, _parse_with_heuristics
from domain.exceptions import IngestionError
from domain.models import Category, ItemStatus
from tests.fakes.fake_memory_port import FakeMemoryPort


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_memory() -> FakeMemoryPort:
    return FakeMemoryPort()


@pytest.fixture
def service(fake_memory: FakeMemoryPort) -> IngestionService:
    return IngestionService(fake_memory)


# ---------------------------------------------------------------------------
# Heuristic parser (no API key required)
# ---------------------------------------------------------------------------

class TestParseWithHeuristics:
    def test_extracts_date_iso(self):
        result = _parse_with_heuristics(
            "Netflix subscription renews on 2025-08-15, $15.99/month"
        )
        assert result["key_date"] == "2025-08-15"

    def test_extracts_price(self):
        result = _parse_with_heuristics("Spotify $9.99/month, trial ends 2025-09-01")
        assert result["price"] == 9.99

    def test_extracts_category_subscription(self):
        result = _parse_with_heuristics("Netflix subscription renews 2025-08-15")
        assert result["category"] == "subscription"

    def test_extracts_category_warranty(self):
        result = _parse_with_heuristics("Apple warranty expires 2026-01-10")
        assert result["category"] == "warranty"

    def test_no_date_falls_back_to_today(self):
        result = _parse_with_heuristics("Some random note with no date")
        assert result["key_date"] == date.today().isoformat()

    def test_no_price_returns_none(self):
        result = _parse_with_heuristics("Free service, renews 2025-12-01")
        assert result["price"] is None


# ---------------------------------------------------------------------------
# IngestionService.remember_item
# ---------------------------------------------------------------------------

class TestIngestionService:
    async def test_remember_item_stores_in_memory(self, service, fake_memory):
        item = await service.remember_item("Netflix subscription renews 2025-08-15, $15.99")
        assert item.item_id in fake_memory.items
        assert item.status == ItemStatus.ACTIVE
        assert item.category == Category.SUBSCRIPTION

    async def test_remember_item_returns_life_admin_item(self, service):
        from domain.models import LifeAdminItem
        item = await service.remember_item("Spotify free_trial ends 2025-09-01")
        assert isinstance(item, LifeAdminItem)

    async def test_remember_item_with_related_ids(self, service, fake_memory):
        item = await service.remember_item(
            "AppleCare warranty expires 2026-01-10",
            related_item_ids=["receipt-001"],
        )
        assert "receipt-001" in item.related_item_ids

    async def test_memory_failure_raises_ingestion_error(self, fake_memory, service):
        fake_memory.should_fail = True
        with pytest.raises(IngestionError):
            await service.remember_item("Netflix subscription renews 2025-08-15")

    async def test_item_is_stored_exactly_once(self, service, fake_memory):
        await service.remember_item("Netflix subscription renews 2025-08-15")
        assert len(fake_memory.items) == 1
