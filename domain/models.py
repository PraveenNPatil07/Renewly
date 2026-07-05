"""
domain/models.py — Pure Python domain model. No framework, no I/O.

LifeAdminItem is the central entity of Renewly. Category is a data field,
not a hardcoded branch, so adding new categories (e.g. "vehicle_registration")
is an additive change to this enum — nothing else in the codebase needs editing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Category(str, Enum):
    """All recognised life-admin categories. Extend here only — OCP."""
    SUBSCRIPTION = "subscription"
    FREE_TRIAL = "free_trial"
    WARRANTY = "warranty"
    INSURANCE = "insurance"
    DOMAIN_RENEWAL = "domain_renewal"
    OTHER = "other"


class ItemStatus(str, Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED_HANDLED = "expired_handled"


@dataclass(frozen=True)
class LifeAdminItem:
    """
    Immutable value object representing one life-admin entry.

    `related_item_ids` is the graph edge that makes the knowledge-graph
    approach earn its keep: a WARRANTY item can point at the receipt item
    for its purchase, enabling cross-entity traversal like
    "show me all warranties for my March laptop purchase."
    """
    item_id: str
    name: str
    category: Category
    vendor: str
    key_date: date           # renewal / expiry / trial-end date
    price: float | None
    notes: str
    status: ItemStatus
    related_item_ids: list[str] = field(default_factory=list)

    def is_stale(self, *, today: date, retention_days: int = 30) -> bool:
        """
        Returns True when the item is no longer ACTIVE and its key_date is
        older than `retention_days` days — indicating it can be pruned from memory.
        """
        if self.status == ItemStatus.ACTIVE:
            return False
        delta = (today - self.key_date).days
        return delta > retention_days

    def days_until_key_date(self, *, today: date) -> int:
        """Positive = in the future; negative = already past."""
        return (self.key_date - today).days


@dataclass(frozen=True)
class ReminderPreference:
    """
    Learned user preference for how many days in advance to remind.

    `last_feedback` carries the raw signal so the feedback service can store
    it back into the graph and let the next improve() call propagate the change.
    """
    lead_days: int
    last_feedback: str | None = None   # "too_early" | "too_late" | "just_right"
