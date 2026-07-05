"""
tests/test_cleanup_service.py — Unit tests for CleanupService.

All tests use FakeMemoryPort — zero Cognee calls.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from application.cleanup_service import CleanupService
from domain.exceptions import CleanupError
from domain.models import Category, ItemStatus, LifeAdminItem
from tests.fakes.fake_memory_port import FakeMemoryPort


@pytest.fixture
def fake_memory() -> FakeMemoryPort:
    return FakeMemoryPort()


@pytest.fixture
def service(fake_memory: FakeMemoryPort) -> CleanupService:
    return CleanupService(fake_memory)


TODAY = date(2025, 8, 1)


def make_item(
    item_id: str,
    status: ItemStatus = ItemStatus.ACTIVE,
    key_date: date = TODAY,
) -> LifeAdminItem:
    return LifeAdminItem(
        item_id=item_id,
        name="Test Item",
        category=Category.SUBSCRIPTION,
        vendor="Vendor",
        key_date=key_date,
        price=None,
        notes="",
        status=status,
        related_item_ids=[],
    )


class TestCleanupService:
    async def test_active_items_are_not_pruned(self, service, fake_memory):
        item = make_item("item-1", ItemStatus.ACTIVE, key_date=TODAY - timedelta(days=60))
        fake_memory.seed(item)
        pruned = await service.run_cleanup([item], today=TODAY, retention_days=30)
        assert pruned == []
        assert "item-1" in fake_memory.items

    async def test_stale_cancelled_items_are_pruned(self, service, fake_memory):
        stale = make_item("item-2", ItemStatus.CANCELLED, key_date=TODAY - timedelta(days=60))
        fake_memory.seed(stale)
        pruned = await service.run_cleanup([stale], today=TODAY, retention_days=30)
        assert "item-2" in pruned
        assert "item-2" not in fake_memory.items

    async def test_recently_expired_items_are_not_pruned(self, service, fake_memory):
        recent = make_item("item-3", ItemStatus.EXPIRED_HANDLED, key_date=TODAY - timedelta(days=10))
        fake_memory.seed(recent)
        pruned = await service.run_cleanup([recent], today=TODAY, retention_days=30)
        assert pruned == []
        assert "item-3" in fake_memory.items

    async def test_returns_list_of_pruned_ids(self, service, fake_memory):
        stale1 = make_item("item-4", ItemStatus.CANCELLED, key_date=TODAY - timedelta(days=60))
        stale2 = make_item("item-5", ItemStatus.EXPIRED_HANDLED, key_date=TODAY - timedelta(days=90))
        fake_memory.seed(stale1)
        fake_memory.seed(stale2)
        pruned = await service.run_cleanup([stale1, stale2], today=TODAY, retention_days=30)
        assert set(pruned) == {"item-4", "item-5"}

    async def test_memory_failure_raises_cleanup_error(self, service, fake_memory):
        stale = make_item("item-6", ItemStatus.CANCELLED, key_date=TODAY - timedelta(days=60))
        fake_memory.seed(stale)
        fake_memory.should_fail = True
        with pytest.raises(CleanupError):
            await service.run_cleanup([stale], today=TODAY, retention_days=30)

    async def test_empty_list_returns_empty(self, service):
        pruned = await service.run_cleanup([], today=TODAY)
        assert pruned == []
