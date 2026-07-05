"""
application/feedback_service.py — Records user feedback to improve reminder timing.

SRP: this service has one job — translate a user's feedback signal into a
     memory improve() call. It does not parse PDFs, it does not query items.

The `improve()` call is the demo's centerpiece: it is the operation that
most naive submissions skip or fake, and it is what makes Renewly a learning
agent rather than a static list tracker.
"""

from __future__ import annotations

import logging

from domain.exceptions import FeedbackError
from memory.port import MemoryPort

logger = logging.getLogger(__name__)

VALID_SIGNALS = frozenset({"too_early", "too_late", "just_right"})


class FeedbackService:
    """
    Records a user's timing feedback for a specific item, triggering an
    improve() call so future reminders adapt.

    Constructor-injected MemoryPort (DIP).
    """

    def __init__(self, memory_port: MemoryPort) -> None:
        self._memory = memory_port

    async def record_feedback(self, item_id: str, signal: str) -> None:
        """
        Persist a feedback signal for `item_id`.

        Args:
            item_id: The item the feedback applies to.
            signal:  One of "too_early", "too_late", "just_right".

        Raises:
            FeedbackError: If the signal is invalid or the improve() call fails.
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
