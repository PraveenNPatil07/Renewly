"""Command-line interface entry point for Renewly.

This module acts as pure interface plumbing with zero business logic. It adheres
strictly to the Single Responsibility Principle for the CLI layer by:
1. Reading the active MemoryPort adapter configuration.
2. Constructing the necessary application services.
3. Delegating the parsed command to the appropriate service.
4. Formatting and printing the result to standard output.

Usage:
    python -m interface.cli add "Netflix subscription renews 2025-08-15, $15.99"
    python -m interface.cli ask "what is expiring this month?"
    python -m interface.cli feedback <item_id> too_early
    python -m interface.cli cleanup
    python -m interface.cli digest

Or via the installed script:
    renewly add "..."
    renewly ask "..."
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

# ---------------------------------------------------------------------------
# Configure logging before any other imports so it applies everywhere
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

# Load .env file so env vars are available without manually exporting them
from dotenv import load_dotenv
load_dotenv()

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError with emoji)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Suppress cosmetic aiohttp warnings from Cognee's internal clients on shutdown
import warnings
warnings.filterwarnings("ignore", message="Unclosed client session")
warnings.filterwarnings("ignore", message="Unclosed connector")

from config import get_memory_adapter
from application.cleanup_service import CleanupService
from application.feedback_service import FeedbackService
from application.ingestion_service import IngestionService
from application.query_service import QueryService
from scheduler.digest_job import run_digest_once

HELP = """
Renewly CLI — Life-Admin Memory Agent

Commands:
  add "<description>"              Ingest a new life-admin item
  ask "<question>"                 Ask a natural-language question
  feedback <item_id> <signal>      Record timing feedback (too_early|too_late|just_right)
  cleanup                          Prune stale/handled items from memory
  digest                           Print a reminder digest of items expiring soon

Environment:
  RENEWLY_BACKEND=local (default)  Use local file-based Cognee
  RENEWLY_BACKEND=cloud            Use Cognee Cloud (requires COGNEE_CLOUD_API_KEY + COGNEE_CLOUD_URL)
  OPENAI_API_KEY                   For LLM-powered text parsing (falls back to heuristics if absent)
""".strip()


def _get_services():
    """Build all application services, injecting the active MemoryPort."""
    memory = get_memory_adapter()
    return (
        IngestionService(memory),
        QueryService(memory),
        FeedbackService(memory),
        CleanupService(memory),
        memory,
    )


async def _cmd_add(args: list[str]) -> int:
    if not args:
        print("Usage: renewly add \"<description>\" [--price <amount>]")
        print("Example: renewly add \"Netflix subscription renews 2025-08-15\" --price 15.99")
        return 1

    args_copy = args.copy()
    price_val = None
    if "--price" in args_copy:
        idx = args_copy.index("--price")
        if idx + 1 < len(args_copy):
            try:
                price_val = float(args_copy[idx + 1].replace("$", ""))
            except ValueError:
                print("[ERROR] Invalid price format")
                return 1
            args_copy.pop(idx + 1)
            args_copy.pop(idx)
        else:
            print("[ERROR] Missing price value")
            return 1

    raw_text = " ".join(args_copy)
    ingestor, _, _, _, _ = _get_services()

    print(f">> Ingesting: {raw_text[:80]}...")
    item = await ingestor.remember_item(raw_text, price=price_val)

    print(f"\n[OK] Stored successfully!")
    print(f"   Item ID  : {item.item_id}")
    print(f"   Name     : {item.name}")
    print(f"   Category : {item.category.value}")
    print(f"   Vendor   : {item.vendor}")
    print(f"   Key Date : {item.key_date}")
    if item.price is not None:
        print(f"   Price    : ${item.price:.2f}")
    if item.related_item_ids:
        print(f"   Related  : {', '.join(item.related_item_ids)}")
    return 0


async def _cmd_ask(args: list[str]) -> int:
    if not args:
        print("Usage: renewly ask \"<question>\"")
        print("Example: renewly ask \"what subscriptions are expiring this month?\"")
        return 1

    question = " ".join(args)
    _, query_svc, _, _, _ = _get_services()

    print(f"[?] Querying: {question}\n")
    answer = await query_svc.ask(question)
    print(answer)
    return 0


async def _cmd_feedback(args: list[str]) -> int:
    if len(args) < 2:
        print("Usage: renewly feedback <item_id> <too_early|too_late|just_right>")
        return 1

    item_id, signal = args[0], args[1]
    _, _, feedback_svc, _, _ = _get_services()

    await feedback_svc.record_feedback(item_id, signal)
    print(f"[OK] Feedback recorded: item {item_id!r} -> {signal!r}")
    print("   The agent will adjust future reminder timing for this category.")
    return 0


async def _cmd_cleanup(args: list[str]) -> int:
    _, query_svc, _, cleanup_svc, memory = _get_services()

    # Retrieve all items to pass to cleanup
    print("[~] Running cleanup -- scanning for stale items...")
    try:
        raw_results = await memory.list_all_items()
    except Exception:
        raw_results = []

    # Convert recall results back to LifeAdminItem for the cleanup service
    from domain.models import Category, ItemStatus, LifeAdminItem
    items = []
    for r in raw_results:
        try:
            item = LifeAdminItem(
                item_id=r.get("item_id", "unknown"),
                name=r.get("name", ""),
                category=Category(r.get("category", "other")),
                vendor=r.get("vendor", ""),
                key_date=date.fromisoformat(r["key_date"]),
                price=r.get("price"),
                notes=r.get("notes", ""),
                status=ItemStatus(r.get("status", "active")),
                related_item_ids=r.get("related_item_ids", []),
            )
            items.append(item)
        except Exception:
            continue

    pruned = await cleanup_svc.run_cleanup(items)

    if pruned:
        print(f"\n[DEL] Pruned {len(pruned)} stale item(s):")
        for pid in pruned:
            print(f"   • {pid}")
    else:
        print("\n[OK] Nothing to prune -- memory is clean.")
    return 0


async def _cmd_digest(args: list[str]) -> int:
    _, query_svc, _, _, _ = _get_services()
    await run_digest_once(query_svc)
    return 0


async def _cmd_cancel(args: list[str]) -> int:
    if not args:
        print("Usage: renewly cancel <item_id>")
        return 1
    item_id = args[0]
    import cognee
    print(f">> Marking item {item_id} as cancelled...")
    # Add a newer chunk with the same ID so the LLM and cleanup service see it as cancelled
    text = (
        f"Life admin item — item_id:{item_id}\n"
        f"Name: (Cancelled Item)\n"
        f"Category: subscription\n"
        f"Vendor: none\n"
        f"Key Date: 1970-01-01\n"
        f"Status: cancelled\n"
        f"Related Items: none\n"
        f"Notes: \n"
    )
    await cognee.add(text, dataset_name="renewly")
    await cognee.cognify()
    print(f"[OK] Item cancelled. Run 'renewly cleanup' to prune.")
    return 0


def main():
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(1)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    logging.getLogger("cognee").setLevel(logging.WARNING)

    # Dispatch to the appropriate handler
    handlers = {
        "add": _cmd_add,
        "ask": _cmd_ask,
        "feedback": _cmd_feedback,
        "cleanup": _cmd_cleanup,
        "digest": _cmd_digest,
        "cancel": _cmd_cancel,
    }

    if cmd not in handlers:
        print(f"Unknown command: {cmd}")
        print(HELP)
        sys.exit(1)

    # Properly run and clean up the asyncio loop to prevent warnings
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        sys.exit(loop.run_until_complete(handlers[cmd](args)))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        logging.debug("Traceback:", exc_info=True)
        sys.exit(1)
    finally:
        # Gracefully close all lingering aiohttp sessions
        import gc
        import aiohttp
        for obj in gc.get_objects():
            if isinstance(obj, aiohttp.ClientSession) and not obj.closed:
                loop.run_until_complete(obj.close())
        loop.run_until_complete(asyncio.sleep(0.1))
        loop.close()


if __name__ == "__main__":
    main()
