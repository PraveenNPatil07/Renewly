"""Service responsible for recording user feedback to improve reminder timing.

This service adheres to the Single Responsibility Principle: its only job is to
translate a user's feedback signal into a memory `improve()` call. It does not
parse input documents or query items.

The `improve()` call is the centerpiece of the agent's learning capability,
allowing Renewly to adapt its reminder cadences over time rather than acting
as a static list tracker.
"""

from __future__ import annotations

import logging

from domain.exceptions import FeedbackError
from memory.port import MemoryPort

logger = logging.getLogger(__name__)

VALID_SIGNALS = frozenset({"too_early", "too_late", "just_right"})


class FeedbackService:
    """Records user timing feedback to adjust future reminders.

    Relies on constructor-injected MemoryPort (Dependency Inversion Principle)
    to perform the underlying `improve()` operation on the graph.

    Attributes:
        _memory: The MemoryPort adapter used for storage operations.
    """

    def __init__(self, memory_port: MemoryPort) -> None:
        """Initializes the FeedbackService.

        Args:
            memory_port: The abstract MemoryPort instance used to interact with
                the underlying graph database.
        """
        self._memory = memory_port

    async def record_feedback(self, item_id: str, signal: str) -> None:
        """Persists a feedback signal for a specific item.

        Args:
            item_id: The unique identifier of the item the feedback applies to.
            signal: The feedback type. Must be one of "too_early", "too_late",
                or "just_right".

        Raises:
            FeedbackError: If the provided signal is invalid or if the
                underlying memory `improve()` call fails.
        """
        if signal not in VALID_SIGNALS:
            raise FeedbackError(
                f"Invalid feedback signal {signal!r}. "
                f"Must be one of: {sorted(VALID_SIGNALS)}"
            )

        feedback = {"item_id": item_id, "signal": signal}
        logger.info("improve item_id=%s signal=%s", item_id, signal)
        try:
            await self._memory.improve(feedback)
        except Exception as exc:
            raise FeedbackError(f"improve() failed: {exc}") from exc
