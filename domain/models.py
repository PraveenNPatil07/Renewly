"""Pure Python domain model defining the core entities of Renewly.

Provides the foundational data structures like `LifeAdminItem` and `Category`
without any external framework or I/O dependencies, ensuring business logic 
remains cleanly decoupled from the underlying storage mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Category(str, Enum):
    """All recognised life-admin categories.

    Categories are implemented as data fields (Enums) rather than class branches
    to adhere to the Open-Closed Principle (OCP). Adding new categories only
    requires appending to this Enum.
    """
    SUBSCRIPTION = "subscription"
    FREE_TRIAL = "free_trial"
    WARRANTY = "warranty"
    INSURANCE = "insurance"
    DOMAIN_RENEWAL = "domain_renewal"
    OTHER = "other"


class ItemStatus(str, Enum):
    """Lifecycle states of a life-admin item."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED_HANDLED = "expired_handled"


@dataclass(frozen=True)
class LifeAdminItem:
    """Immutable value object representing a single life-admin entry.

    `related_item_ids` is the graph edge that enables knowledge-graph traversal.
    For instance, a WARRANTY item can point to the receipt item for its purchase.

    Attributes:
        item_id: Unique identifier for the item.
        name: Human-readable name of the item.
        category: The classification category (e.g., Category.SUBSCRIPTION).
        vendor: The entity providing the item or service.
        key_date: The primary date to track (renewal, expiry, or trial-end).
        price: Financial cost associated with the item, or None if free.
        notes: Additional contextual text for the item.
        status: The lifecycle state of the item (e.g., active, cancelled).
        related_item_ids: List of item IDs this item connects to via graph edges.
    """
    item_id: str
    name: str
    category: Category
    vendor: str
    key_date: date
    price: float | None
    notes: str
    status: ItemStatus
    related_item_ids: list[str] = field(default_factory=list)

    def is_stale(self, *, today: date, retention_days: int = 30) -> bool:
        """Determines if the item is eligible for pruning from memory.

        An item is considered stale if it is no longer ACTIVE and its key_date
        is older than the specified retention window.

        Args:
            today: The reference date to compare against.
            retention_days: Number of days past the key_date before an inactive
                item is considered stale.

        Returns:
            True if the item is stale and can be safely forgotten, False otherwise.
        """
        if self.status == ItemStatus.ACTIVE:
            return False
        delta = (today - self.key_date).days
        return delta > retention_days

    def days_until_key_date(self, *, today: date) -> int:
        """Calculates the number of days from a reference date to the key_date.

        Args:
            today: The reference date.

        Returns:
            The integer number of days. Positive means the key_date is in the
            future; negative means it is in the past.
        """
        return (self.key_date - today).days


@dataclass(frozen=True)
class ReminderPreference:
    """Learned user preference for reminder timing.

    Attributes:
        lead_days: Number of days in advance to remind the user.
        last_feedback: The raw signal ("too_early", "too_late", "just_right")
            so the feedback service can store it back into the graph.
    """
    lead_days: int
    last_feedback: str | None = None
