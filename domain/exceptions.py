"""Domain-specific exception hierarchy for Renewly.

All MemoryPort adapter exceptions are caught at the application layer and
re-raised as one of these types, ensuring the interface layer never sees raw
Cognee or HTTP exceptions. This keeps CLI/API error handling simple and
prevents infrastructure details from leaking upward.
"""


class RenwlyError(Exception):
    """Base class for all Renewly domain exceptions."""


class MemoryOperationError(RenwlyError):
    """Raised when a MemoryPort operation fails for any reason."""


class ItemNotFoundError(RenwlyError):
    """Raised when a requested item does not exist in memory.

    Attributes:
        item_id: The ID of the item that could not be found.
    """
    def __init__(self, item_id: str) -> None:
        """Initializes the ItemNotFoundError.

        Args:
            item_id: The ID of the item that was not found.
        """
        self.item_id = item_id
        super().__init__(f"Item not found: {item_id!r}")


class IngestionError(RenwlyError):
    """Raised when raw text cannot be parsed into a LifeAdminItem."""


class QueryError(RenwlyError):
    """Raised when a recall query fails."""


class FeedbackError(RenwlyError):
    """Raised when recording feedback fails."""


class CleanupError(RenwlyError):
    """Raised when a forget/cleanup operation fails."""
