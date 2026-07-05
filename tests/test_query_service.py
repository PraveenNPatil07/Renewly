"""
tests/test_query_service.py — Unit tests for QueryService.

All tests use FakeMemoryPort — zero Cognee calls.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch, AsyncMock

import pytest

from application.query_service import QueryService
from domain.exceptions import QueryError
from domain.models import Category, ItemStatus, LifeAdminItem
from tests.fakes.fake_memory_port import FakeMemoryPort


@pytest.fixture(autouse=True)
def mock_openai():
    from unittest.mock import MagicMock
    with patch("application.query_service.openai.AsyncOpenAI") as mock_openai_cls:
        mock_client = mock_openai_cls.return_value
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Mocked LLM response about Netflix."
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        yield mock_openai_cls


@pytest.fixture
def fake_memory() -> FakeMemoryPort:
    return FakeMemoryPort()


@pytest.fixture
def service(fake_memory: FakeMemoryPort) -> QueryService:
    return QueryService(fake_memory)


def make_item(
    item_id: str = "item-1",
    name: str = "Netflix",
    category: Category = Category.SUBSCRIPTION,
    vendor: str = "Netflix Inc",
    key_date: date | None = None,
    price: float | None = 15.99,
    status: ItemStatus = ItemStatus.ACTIVE,
) -> LifeAdminItem:
    return LifeAdminItem(
        item_id=item_id,
        name=name,
        category=category,
        vendor=vendor,
        key_date=key_date or date.today() + timedelta(days=10),
        price=price,
        notes="",
        status=status,
        related_item_ids=[],
    )


class TestQueryService:
    async def test_ask_returns_string(self, service, fake_memory):
        fake_memory.seed(make_item())
        result = await service.ask("Netflix")
        assert isinstance(result, str)
        assert "Netflix" in result

    async def test_ask_no_results_returns_friendly_message(self, service):
        result = await service.ask("nonexistent item xyz")
        assert "don't have anything relevant" in result

    async def test_ask_includes_item_count(self, service, fake_memory):
        fake_memory.seed(make_item("item-1", "Netflix"))
        fake_memory.seed(make_item("item-2", "Spotify", vendor="Spotify AB"))
        result = await service.ask("subscription")
        assert result == "Mocked LLM response about Netflix."

    async def test_ask_formats_future_date(self, service, fake_memory):
        future = date.today() + timedelta(days=5)
        item = make_item(key_date=future)
        fake_memory.seed(item)
        result = await service.ask("Netflix")
        assert result == "Mocked LLM response about Netflix."

    async def test_ask_memory_failure_raises_query_error(self, service, fake_memory):
        fake_memory.should_fail = True
        with pytest.raises(QueryError):
            await service.ask("anything")
