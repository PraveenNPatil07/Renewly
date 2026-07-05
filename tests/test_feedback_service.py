"""
tests/test_feedback_service.py — Unit tests for FeedbackService.

All tests use FakeMemoryPort — zero Cognee calls.
"""

from __future__ import annotations

import pytest

from application.feedback_service import FeedbackService
from domain.exceptions import FeedbackError
from tests.fakes.fake_memory_port import FakeMemoryPort


@pytest.fixture
def fake_memory() -> FakeMemoryPort:
    return FakeMemoryPort()


@pytest.fixture
def service(fake_memory: FakeMemoryPort) -> FeedbackService:
    return FeedbackService(fake_memory)


class TestFeedbackService:
    async def test_record_feedback_too_early(self, service, fake_memory):
        await service.record_feedback("item-1", "too_early")
        assert len(fake_memory.feedback_log) == 1
        assert fake_memory.feedback_log[0]["signal"] == "too_early"
        assert fake_memory.feedback_log[0]["item_id"] == "item-1"

    async def test_record_feedback_too_late(self, service, fake_memory):
        await service.record_feedback("item-2", "too_late")
        assert fake_memory.feedback_log[0]["signal"] == "too_late"

    async def test_record_feedback_just_right(self, service, fake_memory):
        await service.record_feedback("item-3", "just_right")
        assert fake_memory.feedback_log[0]["signal"] == "just_right"

    async def test_invalid_signal_raises_feedback_error(self, service):
        with pytest.raises(FeedbackError, match="Invalid feedback signal"):
            await service.record_feedback("item-1", "wrong_signal")

    async def test_memory_failure_raises_feedback_error(self, service, fake_memory):
        fake_memory.should_fail = True
        with pytest.raises(FeedbackError):
            await service.record_feedback("item-1", "too_early")

    async def test_multiple_feedback_entries_accumulate(self, service, fake_memory):
        await service.record_feedback("item-1", "too_early")
        await service.record_feedback("item-1", "just_right")
        assert len(fake_memory.feedback_log) == 2
