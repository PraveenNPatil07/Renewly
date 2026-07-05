"""
scheduler/digest_job.py — Simulated reminder digest.

This is a deliberately simple implementation: a single function that calls
QueryService and logs/prints the result. A production system would plug
this into a task queue (Celery, APScheduler, or a cloud scheduler) and
deliver via email/SMS — but that is explicitly out of scope for the hackathon
(see Non-Goals in the spec).

Why "simulated" is still valuable for the demo:
  - It exercises the full query → recall → format pipeline on a schedule.
  - It proves the scheduler has no business logic of its own (SRP).
  - The output is human-readable, so a judge can verify correctness visually.

Future work (clearly noted, not built):
  - Replace print() with a real notification delivery (email, push, Slack).
  - Use a production-grade task scheduler for reliability.
  - Persist digest history so users can review past digests.
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
