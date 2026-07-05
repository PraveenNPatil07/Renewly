"""Service responsible for executing natural-language queries against memory.

This service adheres to the Single Responsibility Principle: its only job is to
call `recall()` to retrieve relevant items and format those results for humans.
It does NOT parse input, ingest data, or manage reminder timing.
"""

from __future__ import annotations

import logging
from datetime import date
import openai

from domain.exceptions import QueryError
from domain.models import ItemStatus
from memory.port import MemoryPort

logger = logging.getLogger(__name__)


class QueryService:
    """Translates a natural-language question into a formatted human-readable answer.

    Relies on constructor-injected MemoryPort (Dependency Inversion Principle)
    to perform semantic search against the graph.

    Attributes:
        _memory: The MemoryPort adapter used for storage operations.
    """

    def __init__(self, memory_port: MemoryPort) -> None:
        """Initializes the QueryService.

        Args:
            memory_port: The abstract MemoryPort instance used to interact with
                the underlying graph database.
        """
        self._memory = memory_port

    async def ask(self, question: str) -> str:
        """Asks a natural-language question and returns a conversational answer.

        This implements a "filter-then-format" pattern:
        1. The MemoryPort filters the entire graph down to a few semantically relevant items.
        2. The LLM is used strictly to format those specific items into a human-readable
           narrative, preventing hallucination by tightly constraining its context window.

        Args:
            question: The user's query, e.g. "what subscriptions do I have?".

        Returns:
            A formatted string answer provided by the LLM.

        Raises:
            QueryError: If the memory recall operation fails.
        """
        logger.info("recall query=%r", question[:80])
        try:
            results = await self._memory.recall(question)
        except Exception as exc:
            raise QueryError(f"Recall failed: {exc}") from exc

        if not results:
            return "I don't have anything relevant in memory."

        import os

        api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        endpoint = os.getenv("LLM_ENDPOINT")
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        client_kwargs = {"api_key": api_key}
        if endpoint:
            client_kwargs["base_url"] = endpoint
            
        client = openai.AsyncOpenAI(**client_kwargs)

        system_prompt = (
            "You are a helpful assistant. You have been provided with a list of "
            "relevant items retrieved from the user's memory. Your ONLY job is to "
            "narrate these items in a conversational, helpful tone to answer the user's question.\n"
            "Do NOT invent new items. Do NOT evaluate relevance (assume they are relevant). "
            f"Today is {date.today().isoformat()}."
        )

        user_content = f"User Question: {question}\n\nItems from memory:\n"
        for r in results:
            user_content += f"- Name: {r.get('name')}, Category: {r.get('category')}, Date: {r.get('key_date')}, Price: {r.get('price')}, Status: {r.get('status')}\n"

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3
            )
            content = response.choices[0].message.content
            return content.strip() if content else ""
        except Exception as exc:
            logger.error("LLM formatting failed: %s", exc)
            return "I found some relevant items, but couldn't format them right now."
