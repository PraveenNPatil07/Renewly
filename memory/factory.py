"""
memory/factory.py — get_memory_adapter(): the local/cloud toggle.

This single function is the entire "dual prize track" strategy:
  RENEWLY_BACKEND=local  → LocalCogneeAdapter  (open-source track)
  RENEWLY_BACKEND=cloud  → CloudCogneeAdapter  (cloud track)

Nothing else in the codebase changes between the two modes.
"""

from __future__ import annotations

import os

from memory.port import MemoryPort


def get_memory_adapter() -> MemoryPort:
    """
    Read RENEWLY_BACKEND env var and return the corresponding MemoryPort adapter.

    Raises:
        ValueError: If RENEWLY_BACKEND is set to an unrecognised value.
        KeyError:   If required cloud env vars are missing when backend=cloud.
    """
    backend = os.getenv("RENEWLY_BACKEND", "local").lower().strip()

    if backend == "local":
        from memory.local_adapter import LocalCogneeAdapter
        return LocalCogneeAdapter()

    if backend == "cloud":
        api_key = os.environ["COGNEE_CLOUD_API_KEY"]    # raises KeyError if missing
        url = os.environ["COGNEE_CLOUD_URL"]            # raises KeyError if missing
        tenant_id = os.environ.get("COGNEE_CLOUD_TENANT_ID")
        user_id = os.environ.get("COGNEE_CLOUD_USER_ID")
        from memory.cloud_adapter import CloudCogneeAdapter
        return CloudCogneeAdapter(url=url, api_key=api_key, tenant_id=tenant_id, user_id=user_id)

    raise ValueError(
        f"Unknown RENEWLY_BACKEND value: {backend!r}. "
        "Set RENEWLY_BACKEND to 'local' or 'cloud'."
    )
