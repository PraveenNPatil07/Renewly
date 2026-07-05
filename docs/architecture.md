# Renewly — Architecture Reference

This document is the architectural source of truth for the Renewly codebase. It is committed alongside the code so future contributors (and hackathon judges) can understand *why* the code is structured the way it is, not just *how*.

---

## Problem Statement

Life-admin items — subscriptions, warranties, free trials, insurance policies, domain renewals — are scattered across emails, paper receipts, and memory. Existing trackers (Bobby, Rocket Money) treat these as flat line items. They cannot answer:

> *"What electronics do I still have warranty coverage on, and which of those relate to the laptop I bought in March?"*

Answering that requires understanding **relationships between entities across time**. A knowledge graph models these relationships as first-class data. A relational database bolts them on with foreign keys. That is the architectural justification for Cognee.

---

## Architecture Decision Records (ADRs)

| Decision | Context | Rationale | Consequences |
|----------|---------|-----------|--------------|
| **1. Use Cognee (Knowledge Graph) over Relational DB** | Tracking items with temporal and inter-item relationships (e.g., warranty tied to device). | A graph database models relationships natively, allowing complex queries ("what warranties apply to the laptop I bought in March?"). Cognee simplifies vector/graph hybrid workflows. | Requires parsing data into distinct entities/edges. Vendor lock-in minimized by abstracting behind `MemoryPort`. |
| **2. Five-Layer Architecture (DIP)** | Need to support both local and cloud modes seamlessly, and ensure high testability. | Strict separation of concerns (Interface, Application, Domain, Port, Adapter) means business logic doesn't depend on infrastructure. | slightly more boilerplate (interfaces/adapters), but enables instant local/cloud switching and zero-latency unit tests. |
| **3. LLM Parsing with Heuristic Fallback** | Raw input is messy, but relying solely on LLMs can be brittle or expensive. | Try LLM first for best accuracy (via OpenRouter/OpenAI), but fall back to deterministic regex if no API key is set or the call fails. | Ensures the app always works gracefully even in completely offline/unconfigured environments. |
| **4. Simulated Scheduler** | Need to demonstrate background reminders without complex infrastructure (Redis/Celery) for the hackathon. | An `asyncio` loop running `run_digest_once` proves the pipeline works without the operational burden of a real queue. | Not production-ready; would lose jobs on restart. Clear upgrade path to APScheduler/Celery documented. |

---

## Five-Layer Architecture

```
┌─────────────────────────────────────────────┐
│  Interface Layer  (cli.py / api.py)          │
├─────────────────────────────────────────────┤
│  Application Layer  (ingestion/query/...)    │
├─────────────────────────────────────────────┤
│  Domain Layer  (models.py / exceptions.py)   │
├─────────────────────────────────────────────┤
│  Memory Abstraction  (MemoryPort ABC)         │
├─────────────────────────────────────────────┤
│  Memory Implementations  (local / cloud)     │
└─────────────────────────────────────────────┘
```

Each layer depends only on the layer "below" it via abstractions, never concrete implementations. This is the **Dependency Inversion Principle** (SOLID "D") applied systemically.

### Layer Responsibilities

| Layer | Files | Responsibility |
|-------|-------|----------------|
| Interface | `interface/cli.py`, `interface/api.py` | Parse I/O, call services, return results. Zero business logic. |
| Application | `application/*.py` | Orchestrate workflows. Each service has one job (SRP). |
| Domain | `domain/models.py`, `domain/exceptions.py` | Pure Python entities. No framework, no I/O. |
| Memory Abstraction | `memory/port.py` | Abstract interface. The only thing app layer imports. |
| Memory Impl | `memory/local_adapter.py`, `memory/cloud_adapter.py` | Concrete Cognee clients. Only files that `import cognee`. |

---

## The MemoryPort Interface

```python
class MemoryPort(ABC):
    async def remember(self, item: LifeAdminItem) -> None: ...
    async def recall(self, query: str) -> list[dict]: ...
    async def improve(self, feedback: dict) -> None: ...
    async def forget(self, item_id: str) -> None: ...
```

Exactly four methods — the four lifecycle operations this project uses. No speculative methods (Interface Segregation Principle). Both `LocalCogneeAdapter` and `CloudCogneeAdapter` implement this interface identically from the caller's perspective (Liskov Substitution Principle).

---

## The Local/Cloud Toggle

```
RENEWLY_BACKEND=local  →  LocalCogneeAdapter   (SQLite + LanceDB + local graph)
RENEWLY_BACKEND=cloud  →  CloudCogneeAdapter   (Cognee Cloud API)
```

The toggle is implemented in `memory/factory.py`:

```python
def get_memory_adapter() -> MemoryPort:
    backend = os.getenv("RENEWLY_BACKEND", "local")
    if backend == "local":
        return LocalCogneeAdapter()
    if backend == "cloud":
        return CloudCogneeAdapter(url=..., api_key=...)
```

**Nothing else in the codebase changes between modes.** This satisfies both hackathon prize tracks (open-source Cognee, Cognee Cloud) with one design.

---

## SOLID Applied Concretely

### S — Single Responsibility
- `IngestionService`: parse text → store. Does not decide reminder timing.
- `QueryService`: recall + format. Does not parse PDFs.
- `FeedbackService`: validate signal + call `improve()`. Does not format output.
- `CleanupService`: detect stale items + call `forget()`. Does not parse input.

### O — Open/Closed
Adding a new category (e.g. `VEHICLE_REGISTRATION`) requires adding one enum value to `Category` in `domain/models.py`. No branching logic (`if category == ...`) exists anywhere in the codebase — category is always a data field.

### L — Liskov Substitution
`LocalCogneeAdapter` and `CloudCogneeAdapter` are interchangeable. Application code never checks which is active. Both raise the same exception types on failure.

### I — Interface Segregation
`MemoryPort` has exactly four methods — the ones this project actually uses. No speculative additions.

### D — Dependency Inversion
Application services import `MemoryPort` (abstract). Only the adapters import `cognee` (concrete). `config.py` / `factory.py` wire the correct adapter at startup.

---

## Domain Model

### `LifeAdminItem`

The central entity. Frozen dataclass (immutable value object).

```python
@dataclass(frozen=True)
class LifeAdminItem:
    item_id: str
    name: str
    category: Category       # data field, not a code branch
    vendor: str
    key_date: date           # renewal / expiry / trial-end date
    price: float | None
    notes: str
    status: ItemStatus
    related_item_ids: list[str]  # ← graph edges
```

`related_item_ids` is the field that earns the knowledge-graph approach its place: a warranty item points at its purchase receipt, enabling cross-entity graph traversal.

### `Category` Enum

```python
class Category(str, Enum):
    SUBSCRIPTION = "subscription"
    FREE_TRIAL = "free_trial"
    WARRANTY = "warranty"
    INSURANCE = "insurance"
    DOMAIN_RENEWAL = "domain_renewal"
    OTHER = "other"
```

Extending to new categories: add an entry here. Nothing else changes.

---

## Testing Strategy

### Unit Tests (fast, no network)

```
tests/
├── fakes/fake_memory_port.py    # in-memory dict-backed MemoryPort
├── test_ingestion_service.py
├── test_query_service.py
├── test_feedback_service.py
└── test_cleanup_service.py
```

All tests inject `FakeMemoryPort`. No Cognee, no LLM, no network. Run in < 1 second.

```bash
python -m pytest tests/ -v
```

### Manual Integration Tests

A single smoke test per backend (see README). Full integration tests against live Cognee Cloud are explicitly out of scope for the hackathon — the unit tests are sufficient to demonstrate architectural correctness.

---

## Error Handling

All `MemoryPort` calls are wrapped in application services. Raw adapter exceptions are caught and re-raised as domain exceptions (`MemoryOperationError`, `ItemNotFoundError`, etc.) from `domain/exceptions.py`. The interface layer only ever sees domain exceptions — never raw Cognee or HTTP errors.

---

## Scalability Path (future work, not built)

Multi-tenancy would require:
1. Add `user_id` to `LifeAdminItem` and every `MemoryPort` call.
2. Namespace Cognee dataset per user: `dataset_name=f"renewly_{user_id}"`.
3. Add auth middleware at the interface layer.

No domain or application layer changes required — that is the point of the architecture.

---

## What Is Deliberately NOT Built

| Not built | Why |
|-----------|-----|
| OAuth email ingestion | Scope: input is manual text for this version |
| Real push notifications | Scope: digest is simulated (print/log) |
| Multi-user auth | Scope: single-user hackathon demo |
| Frontend framework | Scope: CLI + static HTML only |
| Production task queue | Scope: `asyncio.sleep` loop is sufficient for demo |

These are deliberate cuts, not omissions. A hackathon demo needs depth on the core memory lifecycle, not breadth across integrations a judge won't evaluate.
