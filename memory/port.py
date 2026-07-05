"""The MemoryPort abstract interface for Renewly.

This module defines the contract that all storage backends (local, cloud, etc.)
must satisfy. It enforces the Dependency Inversion Principle: application services
depend only on this abstract interface, never on a concrete client. This ensures
high testability and seamless backend toggling.
"""

from abc import ABC, abstractmethod
from typing import Any

from domain.models import LifeAdminItem


class MemoryPort(ABC):
    """Abstract memory interface. Inject this; never import a concrete adapter."""

    @abstractmethod
    async def remember(self, item: LifeAdminItem) -> None:
        """Ingests a structured LifeAdminItem into the memory graph.

        Args:
            item: The LifeAdminItem to store.

        Raises:
            MemoryOperationError: If the underlying storage operation fails.
        """

    @abstractmethod
    async def recall(self, query: str) -> list[dict]:
        """Answers a natural-language query against the memory graph.

        This method applies semantic relevance filtering to return only items
        that match the semantic intent of the query.

        Args:
            query: The user's natural language question.

        Returns:
            A list of result dictionaries normalised to a consistent shape.

        Raises:
            QueryError: If the search operation fails.
        """

    @abstractmethod
    async def improve(self, feedback: dict) -> None:
        """Adjusts stored preferences based on a user feedback signal.

        Args:
            feedback: A dictionary containing at minimum "item_id" (str) and
                "signal" ("too_early" | "too_late" | "just_right").

        Raises:
            FeedbackError: If the feedback recording fails.
        """

    # We deliberately split list_all_items() from recall() to bypass semantic search.
    # The cleanup service needs to inspect absolutely everything in memory to find
    # stale items. If we routed this through recall(), valid stale items would be
    # filtered out by the vector relevance threshold simply because they didn't semantically
    # match a search query. list_all_items() avoids this relevance filter completely
    # (e.g. by using a raw text-match enumeration like cognee.search("item_id:")).
    @abstractmethod
    async def list_all_items(self) -> list[dict[str, Any]]:
        """Retrieves all items currently stored in memory without semantic filtering.

        Returns:
            A list of dictionary representations of all items.
        """

    @abstractmethod
    async def forget(self, item_id: str) -> None:
        """Prunes a specific item from active memory by its item_id.

        Args:
            item_id: The unique identifier of the item to delete.

        Raises:
            ItemNotFoundError: If the item_id does not exist.
            MemoryOperationError: On other storage failures.
        """
