# Contributing to Renewly

Welcome! Thank you for considering contributing to Renewly. We want to keep this project easy to maintain, highly decoupled, and well-documented.

## Running Tests

Testing is a core priority for this project. We have separated the unit tests (which run instantly via mocked layers) from the integration tests (which make actual network calls to LLMs and databases).

- **Fast Unit Tests**:
  ```bash
  pytest tests/
  ```
  These tests should take less than a second to run. They use the `FakeMemoryPort` instead of real Cognee.

- **Slow Integration Tests**:
  ```bash
  pytest tests/ -m integration
  ```
  Run these tests before submitting a PR to ensure End-to-End correctness.

## Docstring Conventions

We enforce **Google-style docstrings** across the entire codebase. Every public class, function, and module must have a docstring that explains *what it achieves* and *how it works*, rather than restating the signature.

Example:
```python
def remember_item(self, raw_text: str) -> LifeAdminItem:
    """Parse raw text into a structured item and store it in memory.

    Uses an LLM extraction step to pull structured fields (name, vendor, category,
    key date, price) out of free-form text, falling back to regex heuristics if the
    LLM call fails or is unavailable.

    Args:
        raw_text: Free-form description of the item, e.g. "Netflix subscription
            renews 2026-07-15, $15.99/month".

    Returns:
        The structured LifeAdminItem that was stored.

    Raises:
        IngestionError: If the text cannot be parsed into a valid item.
    """
```

## The Layering Rule (Crucial)

Renewly uses a strict Dependency Inversion architecture to decouple logic from the Cognee graph implementation. 

**Rule:** You may **NOT** import or call `cognee` directly outside of `memory/local_adapter.py` and `memory/cloud_adapter.py`. 

All application logic (`application/`) must only ever interact with the abstract `MemoryPort`. If you need new functionality from Cognee, define it in `MemoryPort` first, then implement it in both adapters. This guarantees the seamless toggle between local and cloud modes.
