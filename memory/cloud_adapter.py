"""Cloud-based memory adapter for Renewly using Cognee Cloud.

Connects to a hosted Cognee instance (1.2.2 API). This allows seamless switching 
between local and cloud modes via the RENEWLY_BACKEND environment variable.

Connection details (from platform.cognee.ai/api-keys):
  - COGNEE_CLOUD_URL: API Base URL (tenant-specific URL)
  - COGNEE_CLOUD_API_KEY: API Key (X-Api-Key header)
  - COGNEE_CLOUD_TENANT_ID: Tenant ID (X-Tenant-Id header)
  - COGNEE_CLOUD_USER_ID: User ID (optional)

LLM configuration leverages the same LLM_* environment variables as the local mode.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from domain.exceptions import (
    FeedbackError,
    ItemNotFoundError,
    MemoryOperationError,
    QueryError,
)
from domain.models import LifeAdminItem
from memory.port import MemoryPort

logger = logging.getLogger(__name__)


class CloudCogneeAdapter(MemoryPort):
    """MemoryPort implementation backed by Cognee Cloud (1.2.2).

    Adheres strictly to the MemoryPort contract (LSP), ensuring no semantic
    differences compared to the LocalCogneeAdapter.

    Attributes:
        _url: The Cognee Cloud API Base URL.
        _api_key: The authentication key for Cognee Cloud.
        _tenant_id: The tenant identifier.
        _user_id: Optional user identifier for namespacing.
        _initialized: Boolean flag indicating if lazy initialization has occurred.
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """Initializes the adapter with cloud connection details.

        Args:
            url: The Cognee Cloud API Base URL.
            api_key: The authentication key for Cognee Cloud.
            tenant_id: The tenant identifier.
            user_id: Optional user identifier for namespacing.
        """
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Performs lazy initialization of Cognee Cloud configuration.

        Ensures Cognee is configured exactly once before the first operation.
        Sets up LLM endpoints, API keys, and cloud authentication headers.
        """
        if self._initialized:
            return

        import cognee
        from memory.local_adapter import _configure_llm

        # ── Cognee Cloud auth env vars (picked up by cognee SDK internals) ─
        os.environ["COGNEE_API_KEY"] = self._api_key
        os.environ["COGNEE_BASE_URL"] = self._url

        if self._tenant_id:
            os.environ["COGNEE_TENANT_ID"] = self._tenant_id
            if hasattr(cognee.config, "set_llm_config"):
                pass  # tenant handled via env var

        if self._user_id:
            os.environ["COGNEE_USER_ID"] = self._user_id

        # ── LLM + Embedding config (OpenRouter or OpenAI) ─────────────────
        _configure_llm(cognee)

        # Skip connection test — avoids 30s timeout on startup
        os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")

        self._initialized = True
        logger.info(
            "CloudCogneeAdapter initialized — url=%s tenant=%s",
            self._url,
            self._tenant_id or "n/a",
        )

    async def remember(self, item: LifeAdminItem) -> None:
        """Ingests a structured LifeAdminItem into the cloud memory graph.

        Args:
            item: The LifeAdminItem to store.

        Raises:
            MemoryOperationError: If the ingestion operation fails.
        """
        try:
            await self._ensure_initialized()
            import cognee
            from memory.local_adapter import _item_to_text

            text = _item_to_text(item)
            await cognee.add(text, dataset_name="renewly")
            await cognee.cognify()
            logger.info("remember[cloud] item_id=%s", item.item_id)
        except Exception as exc:
            logger.error("remember[cloud] failed: %s", exc)
            raise MemoryOperationError(f"Cloud remember failed: {exc}") from exc

    async def recall(self, query: str) -> list[dict[str, Any]]:
        """Answers a natural-language query against the cloud memory graph.

        Args:
            query: The user's natural language question.

        Returns:
            A list of result dictionaries normalised to a consistent shape.

        Raises:
            QueryError: If the search operation fails.
        """
        try:
            await self._ensure_initialized()
            import cognee
            from memory.local_adapter import _normalise_results
            from cognee.infrastructure.databases.vector.embeddings.get_embedding_engine import get_embedding_engine

            results = await cognee.search(
                query,
                query_type=cognee.SearchType.CHUNKS,
            )
            items = _normalise_results(results)

            if not items:
                return []

            engine = get_embedding_engine()
            query_vector = (await engine.embed_text([query]))[0]

            filtered_items = []
            logger.info(f"--- Distances for query: '{query}' ---")
            for item in items:
                chunk_str = (
                    f"Life admin item — item_id:{item.get('item_id')}\n"
                    f"Name: {item.get('name')}\n"
                    f"Category: {item.get('category')}\n"
                    f"Vendor: {item.get('vendor')}\n"
                    f"Key Date: {item.get('key_date')}\n"
                )
                item_vector = (await engine.embed_text([chunk_str]))[0]
                dot = sum(a * b for a, b in zip(query_vector, item_vector))
                norm_a = sum(a * a for a in query_vector) ** 0.5
                norm_b = sum(b * b for b in item_vector) ** 0.5
                dist = 1.0 - (dot / (norm_a * norm_b))
                
                logger.info(f"Distance: {dist:.4f} | Item: {item.get('name')}")
                
                # We enforce a strict cosine distance threshold of 0.85 for semantic relevance.
                # In dense vector space (1536d), anything >0.85 distance (or <0.15 similarity)
                # is generally too semantically distant to be considered a true match to the
                # user's intent. This prevents false positives from polluting the LLM's context window.
                if dist < 0.85:
                    filtered_items.append(item)

            logger.info("recall[cloud] query=%r hits=%d filtered=%d", query[:60], len(results), len(filtered_items))
            return _normalise_results(filtered_items)
        except Exception as exc:
            logger.error("Cloud search failed: %s", exc)
            return []

    async def list_all_items(self) -> list[dict[str, Any]]:
        """Retrieves all items currently stored in cloud memory without semantic filtering.

        Returns:
            A list of dictionary representations of all items.
        """
        try:
            await self._ensure_initialized()
            import cognee
            from memory.local_adapter import _normalise_results
            results = await cognee.search(
                "item_id:",
                query_type=cognee.SearchType.CHUNKS,
            )
            return _normalise_results(results)
        except Exception as exc:
            logger.error("list_all_items[cloud] failed: %s", exc)
            return []

    async def improve(self, feedback: dict) -> None:
        """Adjusts stored preferences based on a user feedback signal.

        Args:
            feedback: A dictionary containing at minimum "item_id" and "signal".

        Raises:
            FeedbackError: If the feedback recording fails.
        """
        try:
            await self._ensure_initialized()
            import cognee

            item_id = feedback.get("item_id", "unknown")
            signal = feedback.get("signal", "unknown")
            text = (
                f"User feedback for item {item_id}: reminder was {signal}. "
                f"Adjust reminder lead time accordingly."
            )
            await cognee.add(text, dataset_name="renewly")
            await cognee.cognify()
            logger.info("improve[cloud] item_id=%s signal=%s", item_id, signal)
        except Exception as exc:
            logger.error("improve[cloud] failed: %s", exc)
            raise FeedbackError(f"Cloud improve failed: {exc}") from exc

    async def forget(self, item_id: str) -> None:
        """Prunes a specific item from active cloud memory by its item_id.

        Args:
            item_id: The unique identifier of the item to delete.

        Raises:
            ItemNotFoundError: If the item_id does not exist in memory.
            MemoryOperationError: On other storage failures.
        """
        try:
            await self._ensure_initialized()
            import cognee
            from memory.local_adapter import _normalise_results

            results = await cognee.search(
                f"item_id:{item_id}",
                query_type=cognee.SearchType.CHUNKS,
            )
            if not results:
                raise ItemNotFoundError(item_id)

            text = f"DELETED item_id:{item_id} — removed from active memory."
            await cognee.add(text, dataset_name="renewly")
            await cognee.cognify()
            logger.info("forget[cloud] item_id=%s", item_id)
        except ItemNotFoundError:
            raise
        except Exception as exc:
            logger.error("forget[cloud] failed: %s", exc)
            raise MemoryOperationError(f"Cloud forget failed: {exc}") from exc
