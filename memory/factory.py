"""Factory for instantiating the correct MemoryPort adapter.

This module encapsulates the "dual prize track" toggle logic.
By changing the `RENEWLY_BACKEND` environment variable, the application
switches seamlessly between local and cloud modes without changing any
business logic.
"""

from __future__ import annotations

import os

from memory.port import MemoryPort


def get_memory_adapter() -> MemoryPort:
    """Reads the RENEWLY_BACKEND environment variable and returns the corresponding adapter.

    Returns:
        An instantiated MemoryPort (either LocalCogneeAdapter or CloudCogneeAdapter).

    Raises:
        ValueError: If RENEWLY_BACKEND is set to an unrecognised value.
        KeyError: If required cloud environment variables (e.g. COGNEE_CLOUD_API_KEY)
            are missing when backend is set to 'cloud'.
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
