"""
memory/cloud_adapter.py — CloudCogneeAdapter: wraps Cognee Cloud.

Updated for Cognee 1.2.2 API.

Connection details come from platform.cognee.ai/api-keys → "Connection Details":
  - API Base URL  → COGNEE_CLOUD_URL       (tenant-specific URL)
  - API Key       → COGNEE_CLOUD_API_KEY   (X-Api-Key header)
  - Tenant ID     → COGNEE_CLOUD_TENANT_ID (X-Tenant-Id header)
  - User ID       → COGNEE_CLOUD_USER_ID   (optional)

LLM can be OpenRouter or OpenAI — controlled by the same LLM_* env vars
as local mode (see local_adapter._configure_llm for details).
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
    """
    MemoryPort implementation backed by Cognee Cloud (1.2.2).

    LSP: same method signatures and exception types as LocalCogneeAdapter.
    Application code is entirely unaware which adapter is active.
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._tenant_id = tenant_id
        self._user_id = user_id
        self._initialized = False

    async def _ensure_initialized(self) -> None:
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
                if dist < 0.85:
                    filtered_items.append(item)

            logger.info("recall[cloud] query=%r hits=%d filtered=%d", query[:60], len(results), len(filtered_items))
            return _normalise_results(filtered_items)
        except Exception as exc:
            logger.error("Cloud search failed: %s", exc)
            return []

    async def list_all_items(self) -> list[dict[str, Any]]:
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
