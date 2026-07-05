"""
memory/port.py — The MemoryPort abstract interface.

This is the most important file in the project. Everything in the application
and domain layers depends on this interface — never on a concrete Cognee client.
That is the Dependency Inversion Principle applied for real:

  - Business logic (services) → imports MemoryPort (abstract)
  - Adapters (local, cloud)   → implement MemoryPort (concrete)
  - Config / factory          → wires the correct adapter at startup

Adding a new backend (e.g. Pinecone, Weaviate) means writing one new class
that satisfies this interface. No existing code changes.

The interface is intentionally narrow (ISP): exactly the four lifecycle
operations this project actually uses. No speculative methods.
"""

from abc import ABC, abstractmethod
from typing import Any

from domain.models import LifeAdminItem


class MemoryPort(ABC):
    """Abstract memory interface. Inject this; never import a concrete adapter."""

    @abstractmethod
    async def remember(self, item: LifeAdminItem) -> None:
        """
        Ingest a structured LifeAdminItem into the memory graph.

        Raises:
            domain.exceptions.MemoryOperationError on failure.
        """

    @abstractmethod
    async def recall(self, query: str) -> list[dict]:
        """
        Answer a natural-language query against the memory graph.

        Returns a list of result dicts (keys vary by backend — adapter is
        responsible for normalising to a consistent shape).

        Raises:
            domain.exceptions.QueryError on failure.
        """

    @abstractmethod
    async def improve(self, feedback: dict) -> None:
        """
        Adjust stored preferences or weights based on a user feedback signal.

        `feedback` must contain at minimum:
            - "item_id": str
            - "signal": "too_early" | "too_late" | "just_right"

        Raises:
            domain.exceptions.FeedbackError on failure.
        """

    @abstractmethod
    async def list_all_items(self) -> list[dict[str, Any]]:
        """
        Retrieve all items currently stored in memory.

        Returns:
            A list of dictionary representations of all items.
        """

    @abstractmethod
    async def forget(self, item_id: str) -> None:
        """
        Prune a specific item from active memory by its item_id.

        Raises:
            domain.exceptions.ItemNotFoundError if item_id does not exist.
            domain.exceptions.MemoryOperationError on other failures.
        """
