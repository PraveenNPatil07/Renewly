"""
application/cleanup_service.py — Prunes stale/handled items from memory.

SRP: this service has one job — find items past their retention window and
     call forget() on each. It does not parse input or format query results.

"Stale" means: status != ACTIVE and key_date is older than `retention_days`
(default 30 days). This prevents the memory from accumulating years of
cancelled subscriptions and expired warranties that are no longer useful.
"""

from __future__ import annotations

import logging
from datetime import date

from domain.exceptions import CleanupError
from domain.models import ItemStatus, LifeAdminItem
from memory.port import MemoryPort

logger = logging.getLogger(__name__)


class CleanupService:
    """
    Identifies and removes stale LifeAdminItems from memory.

    Constructor-injected MemoryPort (DIP) + explicit item list injection
    so tests can control exactly which items exist without needing recall().
    """

    def __init__(self, memory_port: MemoryPort) -> None:
        self._memory = memory_port

    async def run_cleanup(
        self,
        all_items: list[LifeAdminItem],
        *,
        today: date | None = None,
        retention_days: int = 30,
    ) -> list[str]:
        """
        Forget all items that are stale relative to `today`.

        Args:
            all_items:      The full current item list (provided by caller —
                            typically loaded via a query or passed from a cache).
            today:          Reference date (defaults to date.today(); injectable
                            for deterministic tests).
            retention_days: Days past key_date before a non-ACTIVE item is pruned.

        Returns:
            List of item_ids that were forgotten (for logging / demo output).

        Raises:
            CleanupError: If any forget() call fails.
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
