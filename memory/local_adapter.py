"""
memory/local_adapter.py — LocalCogneeAdapter: wraps local file-based Cognee.

Updated for Cognee 1.2.2 API:
  - cognee.config.data_root_directory(path)   replaces old set_data_path()
  - cognee.config.set_llm_provider()          sets LLM provider (openai/litellm)
  - cognee.config.set_llm_api_key()           sets API key
  - cognee.config.set_llm_endpoint()          sets base URL (for OpenRouter etc.)
  - cognee.config.set_llm_model()             sets model name

OpenRouter usage: set LLM_PROVIDER=openai, LLM_API_KEY=<openrouter key>,
  LLM_ENDPOINT=https://openrouter.ai/api/v1, LLM_MODEL=<model slug>.
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


class LocalCogneeAdapter(MemoryPort):
    """
    MemoryPort implementation backed by local (self-hosted) Cognee 1.2.2.

    LSP: satisfies every MemoryPort contract — same signatures, same
    exception types as CloudCogneeAdapter.
    """

    def __init__(self, data_path: str | None = None) -> None:
        self._data_path = data_path or os.getenv(
            "COGNEE_DATA_PATH",
            os.path.join(os.path.expanduser("~"), ".renewly", "cognee_data"),
        )
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazy init — configure Cognee once before first operation."""
        if self._initialized:
            return
        import cognee

        # ── Data path (Cognee 1.2.2 API) ─────────────────────────────────
        cognee.config.data_root_directory(os.path.abspath(self._data_path))

        # ── LLM + Embedding config ────────────────────────────────────────────
        _configure_llm(cognee)

        # Skip connection test — useful when embedding endpoint differs from chat
        os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")

        self._initialized = True
        logger.info("LocalCogneeAdapter initialized at %s", self._data_path)

    async def remember(self, item: LifeAdminItem) -> None:
        try:
            await self._ensure_initialized()
            import cognee

            text = _item_to_text(item)
            await cognee.add(text, dataset_name="renewly")
            await cognee.cognify()
            logger.info("remember[local] item_id=%s", item.item_id)
        except Exception as exc:
            logger.error("remember[local] failed: %s", exc)
            raise MemoryOperationError(f"Local remember failed: {exc}") from exc

    async def recall(self, query: str) -> list[dict]:
        try:
            await self._ensure_initialized()
            import cognee
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
                # We embed the chunk string to get its vector, using the same text Cognee stored
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

            logger.info("recall[local] query=%r hits=%d filtered=%d", query[:60], len(results), len(filtered_items))
            return filtered_items
        except Exception as exc:
            logger.error("recall[local] failed: %s", exc)
            raise QueryError(f"Local recall failed: {exc}") from exc

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
            logger.info("improve[local] item_id=%s signal=%s", item_id, signal)
        except Exception as exc:
            logger.error("improve[local] failed: %s", exc)
            raise FeedbackError(f"Local improve failed: {exc}") from exc

    async def forget(self, item_id: str) -> None:
        try:
            await self._ensure_initialized()
            import cognee

            results = await cognee.search(
                f"item_id:{item_id}",
                query_type=cognee.SearchType.CHUNKS,
            )
            if not results:
                raise ItemNotFoundError(item_id)

            text = f"DELETED item_id:{item_id} — removed from active memory."
            await cognee.add(text, dataset_name="renewly")
            await cognee.cognify()
            logger.info("forget[local] item_id=%s", item_id)
        except ItemNotFoundError:
            raise
        except Exception as exc:
            logger.error("forget[local] failed: %s", exc)
            raise MemoryOperationError(f"Local forget failed: {exc}") from exc

    async def list_all_items(self) -> list[dict[str, Any]]:
        try:
            await self._ensure_initialized()
            import cognee
            results = await cognee.search(
                "item_id:",
                query_type=cognee.SearchType.CHUNKS,
            )
            return _normalise_results(results)
        except Exception as exc:
            logger.error("list_all_items[local] failed: %s", exc)
            return []

# ---------------------------------------------------------------------------
# Shared LLM configuration helper (used by both local and cloud adapters)
# ---------------------------------------------------------------------------

def _configure_llm(cognee_module) -> None:
    """
    Configure the LLM and Embedding provider from environment variables.

    Supports OpenRouter for both chat completions and embeddings.

    Environment variables:
      LLM_API_KEY / OPENROUTER_API_KEY  — API key for LLM (chat)
      LLM_ENDPOINT                       — Base URL (https://openrouter.ai/api/v1)
      LLM_MODEL                          — Chat model slug
      LLM_PROVIDER                       — Provider name (default: openai)

      EMBEDDING_API_KEY                  — API key for embeddings (defaults to LLM key)
      EMBEDDING_ENDPOINT                 — Embedding base URL (defaults to LLM endpoint)
      EMBEDDING_MODEL                    — Embedding model (default: text-embedding-3-small)
      EMBEDDING_PROVIDER                 — Embedding provider (default: openai)
    """
    # ── LLM (chat completions) ────────────────────────────────────────────
    llm_api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
    llm_endpoint = os.getenv("LLM_ENDPOINT")
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_provider = os.getenv("LLM_PROVIDER", "openai")

    if llm_api_key:
        cognee_module.config.set_llm_api_key(llm_api_key)
    if llm_endpoint:
        cognee_module.config.set_llm_endpoint(llm_endpoint)
    cognee_module.config.set_llm_model(llm_model)
    cognee_module.config.set_llm_provider(llm_provider)

    # ── Embedding ─────────────────────────────────────────────────────────
    # Separate from LLM config — Cognee uses LiteLLM for embeddings.
    # If not set, defaults to LLM key/endpoint so OpenRouter is used for both.
    emb_api_key = os.getenv("EMBEDDING_API_KEY") or llm_api_key
    emb_endpoint = os.getenv("EMBEDDING_ENDPOINT") or llm_endpoint
    emb_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    emb_provider = os.getenv("EMBEDDING_PROVIDER", "openai")
    emb_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    if emb_api_key:
        cognee_module.config.set_embedding_api_key(emb_api_key)
    if emb_endpoint:
        cognee_module.config.set_embedding_endpoint(emb_endpoint)
    cognee_module.config.set_embedding_model(emb_model)
    cognee_module.config.set_embedding_provider(emb_provider)
    cognee_module.config.set_embedding_dimensions(emb_dimensions)

    logger.debug(
        "LLM: provider=%s endpoint=%s model=%s | Embedding: provider=%s endpoint=%s model=%s",
        llm_provider, llm_endpoint or "(default)",
        llm_model, emb_provider, emb_endpoint or "(default)", emb_model,
    )



# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _item_to_text(item: LifeAdminItem) -> str:
    """Convert a LifeAdminItem to a rich text document for Cognee ingestion."""
    related = ", ".join(item.related_item_ids) if item.related_item_ids else "none"
    return (
        f"Life admin item — item_id:{item.item_id}\n"
        f"Name: {item.name}\n"
        f"Category: {item.category.value}\n"
        f"Vendor: {item.vendor}\n"
        f"Key Date: {item.key_date.isoformat()}\n"
        f"Price: {'${:.2f}'.format(item.price) if item.price is not None else 'N/A'}\n"
        f"Status: {item.status.value}\n"
        f"Related Items: {related}\n"
        f"Notes: {item.notes}\n"
    )


def _normalise_results(raw: list) -> list[dict]:
    """Normalise heterogeneous Cognee result objects into plain dicts, deduplicating by item_id."""
    normalised = []
    parsed_items = {}
    deleted_item_ids = set()
    
    for r in raw:
        r_dict = r if isinstance(r, dict) else r.__dict__ if hasattr(r, "__dict__") else None
        if not r_dict:
            normalised.append({"raw": str(r)})
            continue
            
        search_res = r_dict.get("search_result")
        if isinstance(search_res, list) and search_res and isinstance(search_res[0], dict):
            # Parse CHUNKS result
            for chunk in search_res:
                text = chunk.get("text", "")
                if text.startswith("DELETED item_id:"):
                    parts = text.split("DELETED item_id:")
                    if len(parts) > 1:
                        deleted_id = parts[1].split(" ")[0].strip()
                        deleted_item_ids.add(deleted_id)
                elif "item_id:" in text:
                    parsed = _parse_chunk_text(text)
                    item_id = parsed.get("item_id")
                    if item_id:
                        if item_id in parsed_items:
                            # If we already have this item, keep the one that is cancelled
                            if parsed.get("status") == "cancelled":
                                parsed_items[item_id] = parsed
                        else:
                            parsed_items[item_id] = parsed
                    else:
                        normalised.append(parsed)
        elif isinstance(search_res, list) and search_res and isinstance(search_res[0], str):
            # Parse GRAPH_COMPLETION result
            normalised.append({"synthesized_answer": search_res[0]})
        elif isinstance(search_res, str):
            normalised.append({"synthesized_answer": search_res})
        else:
            normalised.append(r_dict)
            
    # Remove deleted items
    for deleted_id in deleted_item_ids:
        if deleted_id in parsed_items:
            del parsed_items[deleted_id]

    # Add deduplicated parsed items to normalised list
    normalised.extend(parsed_items.values())
    return normalised


def _parse_chunk_text(text: str) -> dict:
    """Reconstitute a LifeAdminItem dict from the raw chunk text."""
    parsed = {}
    lines = text.split("\n")
    for line in lines:
        if line.startswith("Life admin item") and "item_id:" in line:
            parsed["item_id"] = line.split("item_id:")[1].strip()
        elif ":" in line:
            key, val = line.split(":", 1)
            key = key.strip().lower()
            val = val.strip()
            if key == "name": parsed["name"] = val
            elif key == "category": parsed["category"] = val
            elif key == "vendor": parsed["vendor"] = val
            elif key == "key date": parsed["key_date"] = val
            elif key == "price": 
                if val.startswith("$"): val = val[1:]
                try: parsed["price"] = float(val)
                except ValueError: parsed["price"] = None
            elif key == "status": parsed["status"] = val
            elif key == "related items": 
                if val == "none" or not val: parsed["related_item_ids"] = []
                else: parsed["related_item_ids"] = [x.strip() for x in val.split(",")]
            elif key == "notes": parsed["notes"] = val
    return parsed
