"""
application/query_service.py — Natural-language query against the memory graph.

SRP: this service has one job — call recall() and format results for humans.
     It does NOT parse input or manage reminder timing.
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
    """
    Translates a natural-language question into a memory recall and formats
    the results into a readable, conversational answer.

    Constructor-injected MemoryPort (DIP).
    """

    def __init__(self, memory_port: MemoryPort) -> None:
        self._memory = memory_port

    async def ask(self, question: str) -> str:
        """
        Ask a natural-language question and get a human-readable answer.

        Args:
            question: e.g. "what subscriptions do I have?",
                      "what is expiring in the next 7 days?"

        Returns:
            A formatted string answer.

        Raises:
            QueryError: If the recall operation fails.
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
