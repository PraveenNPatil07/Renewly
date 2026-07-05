"""Service responsible for pruning stale or handled items from memory.

This service adheres to the Single Responsibility Principle: its only job is to
identify items that are past their retention window and remove them via the
MemoryPort.

An item is considered "stale" if its status is not ACTIVE and its key date
is older than the specified retention window (default 30 days). This prevents
memory accumulation of old, irrelevant entries.
"""

from __future__ import annotations

import logging
from datetime import date

from domain.exceptions import CleanupError
from domain.models import ItemStatus, LifeAdminItem
from memory.port import MemoryPort

logger = logging.getLogger(__name__)


class CleanupService:
    """Identifies and removes stale LifeAdminItems from memory.

    Relies on constructor-injected MemoryPort (Dependency Inversion Principle)
    and accepts an explicit item list in `run_cleanup` so that calling layers
    (or tests) control data retrieval.

    Attributes:
        _memory: The MemoryPort adapter used for storage operations.
    """

    def __init__(self, memory_port: MemoryPort) -> None:
        """Initializes the CleanupService.

        Args:
            memory_port: The abstract MemoryPort instance used to interact with
                the underlying graph database.
        """
        self._memory = memory_port

    async def run_cleanup(
        self,
        all_items: list[LifeAdminItem],
        *,
        today: date | None = None,
        retention_days: int = 30,
    ) -> list[str]:
        """Forgets all items that are stale relative to the provided reference date.

        Args:
            all_items: The complete list of current items, typically provided
                by the caller fetching `list_all_items()` from memory.
            today: Reference date for staleness calculations. Defaults to
                date.today() if not provided. Injectable for deterministic tests.
            retention_days: Number of days past an item's key_date before it
                can be pruned, assuming it is not ACTIVE.

        Returns:
            A list of item_ids that were successfully forgotten (for logging
            or UI output).

        Raises:
            CleanupError: If any underlying `forget()` operation fails.
        """
        today = today or date.today()
        pruned: list[str] = []

        for item in all_items:
            if not item.is_stale(today=today, retention_days=retention_days):
                continue
            logger.info("forget item_id=%s", item.item_id)
            try:
                await self._memory.forget(item.item_id)
                pruned.append(item.item_id)
            except Exception as exc:
                raise CleanupError(
                    f"forget() failed for item_id={item.item_id}: {exc}"
                ) from exc

        return pruned
