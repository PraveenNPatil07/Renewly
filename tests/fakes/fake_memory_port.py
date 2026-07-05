"""
tests/fakes/fake_memory_port.py — In-memory MemoryPort for unit tests.

This implementation stores everything in plain Python dicts.  No Cognee,
no LLM, no network — tests run in milliseconds.

The existence of this fake is the empirical proof that the architecture
actually decouples business logic from Cognee: if the layering were wrong,
this fake could not exist, and every test would need a live backend.

LSP guarantee: FakeMemoryPort satisfies every contract documented in
MemoryPort — same method signatures, same exception types on failure.
"""

from __future__ import annotations

from datetime import date

from domain.exceptions import ItemNotFoundError, MemoryOperationError
from domain.models import LifeAdminItem
from memory.port import MemoryPort


class FakeMemoryPort(MemoryPort):
    """
    In-memory MemoryPort implementation.

    Exposes internal state via `items`, `feedback_log`, and `forgotten_ids`
    so tests can inspect what happened without needing to call recall().
    """

    def __init__(self) -> None:
        # item_id → LifeAdminItem
        self.items: dict[str, LifeAdminItem] = {}
        # List of raw feedback dicts passed to improve()
        self.feedback_log: list[dict] = []
        # item_ids passed to forget()
        self.forgotten_ids: list[str] = []
        # Controls whether operations fail — set to True in failure-path tests
        self.should_fail: bool = False

    # ------------------------------------------------------------------
    # MemoryPort implementation
    # ------------------------------------------------------------------

    async def remember(self, item: LifeAdminItem) -> None:
        if self.should_fail:
            raise MemoryOperationError("FakeMemoryPort.remember: simulated failure")
        self.items[item.item_id] = item

    async def recall(self, query: str) -> list[dict]:
        if self.should_fail:
            raise MemoryOperationError("FakeMemoryPort.recall: simulated failure")
        # Naïve keyword match — good enough for unit tests that control input
        q = query.lower()
        results = []
        for item in self.items.values():
            text = f"{item.name} {item.vendor} {item.category} {item.notes}".lower()
            if any(word in text for word in q.split()):
                results.append(self._item_to_dict(item))
        return list(results)

    async def list_all_items(self) -> list[dict]:
        if self.should_fail:
            raise MemoryOperationError("FakeMemoryPort.list_all_items: simulated failure")
        return [
            {
                "item_id": item.item_id,
                "name": item.name,
                "category": item.category.value,
                "vendor": item.vendor,
                "key_date": item.key_date.isoformat(),
                "price": item.price,
                "notes": item.notes,
                "status": item.status.value,
                "related_item_ids": item.related_item_ids,
            }
            for item in self.items.values()
        ]

    async def improve(self, feedback: dict) -> None:
        if self.should_fail:
            raise MemoryOperationError("FakeMemoryPort.improve: simulated failure")
        self.feedback_log.append(feedback)

    async def forget(self, item_id: str) -> None:
        if self.should_fail:
            raise MemoryOperationError("FakeMemoryPort.forget: simulated failure")
        if item_id not in self.items:
            raise ItemNotFoundError(item_id)
        del self.items[item_id]
        self.forgotten_ids.append(item_id)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def seed(self, item: LifeAdminItem) -> None:
        """Directly insert an item without going through remember(), for test setup."""
        self.items[item.item_id] = item

    @staticmethod
    def _item_to_dict(item: LifeAdminItem) -> dict:
        return {
            "item_id": item.item_id,
            "name": item.name,
            "category": item.category.value,
            "vendor": item.vendor,
            "key_date": item.key_date.isoformat(),
            "price": item.price,
            "notes": item.notes,
            "status": item.status.value,
            "related_item_ids": item.related_item_ids,
        }
