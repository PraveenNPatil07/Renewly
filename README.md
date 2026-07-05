# ♻️ Renewly — Life-Admin Memory Agent

> **One codebase. Two backends. Zero forgotten renewals.**

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com)
[![Cognee](https://img.shields.io/badge/Powered_by-Cognee-purple.svg)](https://cognee.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Renewly** is an intelligent, personal memory agent designed to track anything with an expiry, renewal, or deadline attached. Whether it's software subscriptions, free trials, warranties, insurance policies, or domain renewals, Renewly remembers them all and lets you ask natural-language questions about what's coming up.

---

## ✨ Key Features

- 🧠 **Knowledge Graph-Powered Memory**: Models relationships between entities (e.g., a warranty linked to a specific laptop purchase) rather than storing flat lists.
- 🗣️ **Natural Language Interface**: Add items and query your database using everyday language ("What subscriptions are renewing this month?").
- 🔄 **Seamless Backend Switching**: Toggle between local (file-based) and cloud (Cognee Cloud) data stores with a single environment variable—no code changes required.
- 🏗️ **Clean Architecture**: Built using a strict Five-Layer Dependency Inversion Principle design, making it highly testable and extensible.
- 🎓 **Learning Agent**: Incorporates a feedback loop (`improve()`) to adjust reminder timings based on user input, evolving from a static tracker into an adaptive agent.

---

## 🏗️ How It Works (Architecture)

### Why a Knowledge Graph (not a spreadsheet)?
Existing tools like Bobby or Rocket Money track subscriptions as isolated, flat line items. They cannot easily answer questions like:
> *"What electronics do I still have warranty coverage on, and which of those relate to the laptop I bought in March?"*

Answering this requires understanding **relationships between entities across time**. A knowledge graph models these relationships as first-class data (e.g., a warranty linked to a purchase receipt, linked to a vendor). Renewly uses **Cognee** instead of a traditional relational database because **the relationships are the product**.

### The Five-Layer Design (Dependency Inversion Principle)

Renewly's architecture is strictly layered to decouple business logic from infrastructure:

```text
┌─────────────────────────────────────────────┐
│  Interface Layer  (cli.py / api.py)          │  Entry points only — no business logic
├─────────────────────────────────────────────┤
│  Application Layer  (ingestion/query/...)    │  Orchestrates workflows
├─────────────────────────────────────────────┤
│  Domain Layer  (models.py / exceptions.py)   │  Pure Python — no framework, no I/O
├─────────────────────────────────────────────┤
│  Memory Abstraction  (MemoryPort ABC)         │  Abstract Interface — the only thing app imports
├─────────────────────────────────────────────┤
│  Memory Implementations  (local / cloud)     │  Swappable Cognee adapters, chosen by config
└─────────────────────────────────────────────┘
```

**Why this layering matters:**
1. **Lightning-fast tests**: Tests run in milliseconds against a `FakeMemoryPort` (no LLM, no network latency).
2. **Effortless toggling**: Switching between local and cloud is done via a single environment variable (`RENEWLY_BACKEND`).
3. **Future-proof**: Adding a new vector database or backend means writing one new adapter class, with zero changes to existing business logic.

### The Four Memory Lifecycle Operations

Renewly maps directly to four core memory operations:

| Operation | Service | Description |
|-----------|---------|-------------|
| `remember()` | `IngestionService` | Parses raw natural text → `LifeAdminItem` → ingests into the Cognee graph. |
| `recall()` | `QueryService` | Processes a natural-language query and returns a formatted answer. |
| `improve()` | `FeedbackService` | Takes user feedback (e.g., "reminded too early") and adapts future reminder timing. |
| `forget()` | `CleanupService` | Prunes stale items past their retention window. |

---

## 🚀 Quick Start

### 1. Installation

Clone the repository and install the dependencies (including development tools like `pytest`):

```bash
git clone https://github.com/yourusername/renewly.git
cd renewly
pip install -e ".[dev]"
```

### 2. Configuration

Copy the example environment file and configure it:

```bash
cp .env.example .env
```
*Note: At minimum, set your `OPENAI_API_KEY` in `.env` for accurate natural language parsing. If omitted, Renewly falls back to heuristic regex parsing.*

### 3. Usage (Local Mode)

By default, Renewly runs locally without needing cloud credentials. Use the CLI interface to interact with your agent:

```bash
# Add a subscription
python -m interface.cli add "Netflix subscription renews on 2025-08-15, $15.99/month"

# Add a warranty with a graph relationship
python -m interface.cli add "AppleCare+ warranty expires 2026-01-10, for MacBook Pro"

# Ask a natural-language question
python -m interface.cli ask "what subscriptions do I have?"
python -m interface.cli ask "what warranties are expiring in the next 6 months?"

# Record timing feedback (demonstrates the improve() lifecycle)
python -m interface.cli feedback <item_id> too_early

# Run a reminder digest (demonstrates the scheduler)
python -m interface.cli digest

# Prune stale items (demonstrates the forget() lifecycle)
python -m interface.cli cleanup
```

### 4. Usage (Cloud Mode)

Switching to Cognee Cloud is instantaneous. Set your backend and provide your cloud keys:

```bash
export RENEWLY_BACKEND=cloud
export COGNEE_CLOUD_API_KEY=your-key
export COGNEE_CLOUD_URL=https://api.cognee.ai

# Use the exact same commands as above — no code changes needed!
python -m interface.cli ask "what's expiring this month?"
```

### 5. Running the REST API

Renewly also includes a FastAPI server for programmatic access:

```bash
uvicorn interface.api:app --reload --port 8000
```
Then open your browser and navigate to the interactive Swagger documentation at: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧪 Testing

Renewly boasts an extremely fast test suite. All tests run against an in-memory `FakeMemoryPort`, which empirically proves that the business logic is entirely decoupled from Cognee and LLM calls.

```bash
python -m pytest tests/ -v
```

Expected output:
```text
tests/test_ingestion_service.py  ✓  parsing + remember() path
tests/test_query_service.py      ✓  recall() + formatting
tests/test_feedback_service.py   ✓  improve() signal routing
tests/test_cleanup_service.py    ✓  stale detection + forget()
```

---

## 📁 Project Structure

```text
renewly/
├── config.py                     # Env-var reader → MemoryPort adapter mapping
├── domain/
│   ├── models.py                 # Core models: LifeAdminItem, Category, ItemStatus
│   └── exceptions.py             # Domain-specific exception hierarchy
├── memory/
│   ├── port.py                   # MemoryPort ABC (the core interface)
│   ├── local_adapter.py          # Local file-based Cognee implementation
│   ├── cloud_adapter.py          # Cognee Cloud implementation
│   └── factory.py                # Dependency injection factory
├── application/
│   ├── ingestion_service.py      # Parses text → creates LifeAdminItem + remember()
│   ├── query_service.py          # Executes recall() + text formatting
│   ├── feedback_service.py       # Executes improve() + validation
│   └── cleanup_service.py        # Identifies stale items + executes forget()
├── interface/
│   ├── cli.py                    # Command Line Interface (CLI) entry point
│   └── api.py                    # FastAPI routes and endpoints
├── scheduler/
│   └── digest_job.py             # Simulated cron-job for reminder digests
└── tests/
    ├── fakes/fake_memory_port.py # In-memory test double for zero-latency testing
    ├── test_ingestion_service.py
    ├── test_query_service.py
    ├── test_feedback_service.py
    └── test_cleanup_service.py
```

---

## 🔒 Security & Scalability

### Security Notes
- **Secrets Management**: Real API keys should strictly remain in `.env` (which is in `.gitignore`). Only `.env.example` is committed.
- **Production Readiness**: A production deployment requires **encryption at rest** (since life-admin data can include prices and account identifiers) and **per-user namespacing** in the Cognee dataset.

### Scalability Roadmap
Scaling this architecture to a multi-user, multi-tenant system requires only three additive changes (none of which require rewriting the core domain or application layer):
1. Add `user_id` to `LifeAdminItem` and to all `MemoryPort` interface methods.
2. Namespace the underlying Cognee dataset per user (e.g., `dataset_name=f"renewly_{user_id}"`).
3. Add robust authentication middleware at the interface layer (e.g., via FastAPI).

---

## 🔮 Future Work

- **Real-Time Notifications**: Replace standard out `print()` statements in `digest_job.py` with actual Email, Push Notification, or Slack integrations.
- **Automated Document Ingestion**: Introduce an OAuth inbox scanner or PDF text extraction pipeline that automatically feeds data into the `IngestionService`.
- **Production Scheduler**: Upgrade the mock `asyncio.sleep` loop to a robust task queue like Celery, APScheduler, or AWS EventBridge.
