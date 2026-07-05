"""Simulated reminder digest module for Renewly.

This module provides a deliberately simple implementation of a background
scheduler. It consists of functions that invoke the QueryService to
generate and output a digest of upcoming renewals.

For a production environment, this module would be replaced or integrated
with a robust task queue (e.g., Celery, APScheduler, or a cloud scheduler)
and paired with actual delivery mechanisms (Email, SMS, Push). For the
hackathon scope, it demonstrates the pipeline without the operational
overhead of a real queue.

Future improvements:
- Replace standard out printing with a real notification delivery service.
- Use a production-grade task scheduler for reliability.
- Persist digest history to allow users to review past digests.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from application.query_service import QueryService

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 60 * 60 * 8  # 8 hours — configurable
DIGEST_QUERY = "what is expiring in the next 7 days"


async def run_digest_once(
    query_service: QueryService,
    *,
    print_output: bool = True,
) -> str:
    """
    Run a single digest check and return (and optionally print) the result.

    Args:
        query_service: Injected QueryService (already wired to a MemoryPort).
        print_output:  Whether to print to stdout (False for API use).

    Returns:
        The formatted digest string.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"\n{'='*60}\n🗓️  RENEWLY REMINDER DIGEST  [{now}]\n{'='*60}"

    try:
        answer = await query_service.ask(DIGEST_QUERY)
    except Exception as exc:
        logger.error("Digest query failed: %s", exc)
        answer = f"Could not retrieve digest: {exc}"

    footer = "="*60
    digest = f"{header}\n{answer}\n{footer}\n"

    if print_output:
        print(digest)
    logger.info("digest generated at %s", now)
    return digest


async def run_digest_loop(
    query_service: QueryService,
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """
    Run the digest on a recurring interval.

    This is the entry point for a long-running background process.
    For the hackathon demo, use run_digest_once() instead (via CLI or API).

    NOTE: This is intentionally a simple asyncio.sleep loop, not a production
    task queue. See module docstring for future work notes.
    """
    logger.info(
        "Starting digest loop — interval=%ds (%dh)",
        interval_seconds,
        interval_seconds // 3600,
    )
    while True:
        await run_digest_once(query_service)
        logger.info("Next digest in %d seconds", interval_seconds)
        await asyncio.sleep(interval_seconds)
