<p align="center">
  <img src="./apps/web/public/banner.png" alt="Patchwork Banner" width="100%" />
</p>

# PATCHWORK

Event-driven autonomous incident response and self-healing pipeline that ingests production stack traces, retrieves AST-chunked context, verifies patches inside an isolated Docker sandbox, and gates GitHub Pull Requests behind Human-in-the-Loop (HITL) approval.

---

## The Problem & System Design (Why This Exists)

Naive LLM code-fixing scripts fail in production for four predictable reasons: arbitrary character-count chunking slices functions mid-block and strips call-site context; unbounded agent retry loops burn token quotas when a test fails repeatedly; cascading production errors trigger duplicate webhook storms that spawn redundant workers; and executing LLM-generated code on a host runner exposes credentials and internal networks.

Patchwork addresses each failure mode at the infrastructure boundary:

1. **Idempotent Ingestion:** Every incoming stack trace is reduced to a deterministic SHA-256 fingerprint (`error_type:file_path:line_number`) and locked in Redis (`SET key value NX EX 3600`) before touching PostgreSQL or the job queue.
2. **AST-Boundary Retrieval:** Source files are parsed with `tree-sitter` (`tree-sitter-python`) into complete top-level function, class, and decorated definitions, indexed alongside 768-dimensional embeddings in Supabase `pgvector`.
3. **Bounded State Machine:** A cyclic LangGraph workflow (`triage_node` -> `retrieve_node` -> `patch_node` -> `sandbox_node`) enforces a hard ceiling of `max_retries = 3` and logs per-step token usage and latency to PostgreSQL.
4. **Air-Gapped Verification & HITL Gate:** Candidate patches are streamed as in-memory tarballs into a network-disabled Docker container (`network_mode="none"`, `mem_limit="256m"`, `pids_limit=64`) to run `pytest`. Passing patches stop at `AWAITING_APPROVAL` until an operator explicitly approves PR creation from the web dashboard.

---

## Architecture & Data Flow

```mermaid
flowchart LR
    A["Webhook / Client<br/>POST /v1/incidents"] --> B["FastAPI Ingestion<br/>(apps/api)"]
    B --> C["Redis Cloud<br/>NX EX 3600 Dedup + ARQ Queue"]
    C --> D["LangGraph Worker<br/>(apps/worker)"]
    D <--> E["Context Retrieval<br/>GitHub API + Tree-sitter + pgvector"]
    D <--> F["LLM Patch Synthesis<br/>Gemini / Groq Structured Output"]
    D --> G["Guardrail Validator<br/>(packages/core/guardrails.py)"]
    G -- "Violation (>3 files / .env)" --> H["ESCALATED_TO_HUMAN"]
    G -- "Valid Unified Diff" --> I["Local Docker Sandbox<br/>(pytest, net=none, 256MB)"]
    I -- "Tests Fail (retry < 3)" --> F
    I -- "Tests Fail (retry >= 3)" --> J["FAILED_MAX_RETRIES"]
    I -- "Tests Pass" --> K["Next.js HITL Dashboard<br/>(apps/web - AWAITING_APPROVAL)"]
    K -- "POST /approve" --> L["GitHub Pull Request<br/>(patchwork/fix-{id})"]
```

### Component Breakdown & Trade-offs

- **FastAPI + Async SQLAlchemy (`apps/api`):** Non-blocking HTTP ingestion and approval API using `asyncpg` with `statement_cache_size=0` for compatibility with Supabase PgBouncer transaction poolers.
- **Redis Cloud + ARQ (`apps/worker`):** Lightweight async job queue and atomic deduplication store. Chosen over Celery/RabbitMQ to keep memory footprint low and support serverless Redis endpoints (`redis://` and `rediss://`).
- **LangGraph + Pydantic Structured Outputs (`apps/worker/graph`):** Replaces free-form agent loops with an explicit directed graph. The LLM is constrained to return a validated `PatchProposal` schema (`root_cause_explanation`, `unified_diff`, `file_patches`), with automatic fallback from Google Gemini to Groq (`llama-3.3-70b-versatile`) on HTTP 503/504 timeouts.
- **Docker SDK Sandbox (`apps/worker/sandbox/docker_runner.py`):** Uses `put_archive` over the local Docker socket instead of host volume bind-mounts, avoiding cross-OS path translation issues on Windows/WSL2 while keeping the container filesystem isolated.
- **Next.js 14 Dashboard (`apps/web`):** TypeScript App Router interface for inspecting side-by-side diffs (`react-diff-viewer-continued`), node-by-node execution telemetry, Docker `pytest` logs, and triggering PR creation.

---

## Engineering Guardrails & Safety Mechanisms

### 1. Idempotency & Storm Suppression
`apps/api/services/deduplicator.py` extracts the innermost traceback frame (`file_path`, `line_number`) and hashes `f"{error_type}:{file_path}:{line_number}"` with SHA-256. Redis `SET patchwork:incident:dedup:{fingerprint} 1 NX EX 3600` guarantees that a spike of 10,000 identical exceptions in an hour results in exactly one database row and one LLM workflow execution. Suppressed duplicates increment `patchwork:metrics:duplicates_blocked` for live telemetry.

### 2. Blast-Radius Control
`packages/core/guardrails.py` validates every LLM output before sandbox execution and again before GitHub PR creation:
- Rejects patches modifying more than `MAX_FILES_PER_PATCH = 3` files.
- Blocks modifications to `.env*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `.github/*`, `migrations/*`, `alembic/*`, `*secret*`, absolute paths, and `..` path traversals.
- Validates unified diff headers (`--- `, `+++ `, `@@ -start,count +start,count @@`) and hunk body prefixes. Any violation halts the graph and transitions the incident to `ESCALATED_TO_HUMAN`.

### 3. Zero-Network Docker Sandbox
`apps/worker/sandbox/docker_runner.py` executes tests inside `patchwork-sandbox:latest` (`python:3.11-slim` + `pytest`) with strict kernel and runtime limits:
- `network_mode="none"` prevents outbound exfiltration or external network calls during test execution.
- `mem_limit="256m"` and `pids_limit=64` prevent fork bombs and memory exhaustion on the worker host.
- A 30-second execution timeout is enforced, followed by unconditional `container.remove(force=True)` in a `finally` block.

### 4. Bounded Self-Correction
`apps/worker/graph/workflow.py` routes failed `sandbox_node` runs back to `patch_node` with captured `stdout`/`stderr` from `pytest` so the model can self-correct. When `retry_count` reaches `3`, execution terminates immediately with status `FAILED_MAX_RETRIES`.

---

## Repository Structure

```text
patchwork/
├── Dockerfile.sandbox               # Isolated pytest runner image (python:3.11-slim)
├── docker-compose.yml               # Local Postgres (pgvector) + Redis fallback
├── pyproject.toml                   # Pytest configuration
├── .env.example                     # Environment variable template
├── migrations/
│   └── 001_init.sql                 # PostgreSQL schema, enums, pgvector IVFFlat index
├── apps/
│   ├── api/                         # FastAPI service
│   │   ├── main.py                  # App entrypoint, CORS, /health telemetry
│   │   ├── config.py                # Pydantic Settings & Redis DSN parser
│   │   ├── database.py              # AsyncEngine & AsyncSession factory
│   │   ├── models.py                # SQLAlchemy ORM (Incident, AgentTrace, CodeChunk)
│   │   ├── schemas.py               # Pydantic v2 request/response DTOs
│   │   ├── routers/
│   │   │   ├── incidents.py         # POST /v1/incidents, GET /v1/incidents[/{id}]
│   │   │   └── approvals.py         # POST /v1/incidents/{id}/approve|reject
│   │   └── services/
│   │       ├── deduplicator.py      # SHA-256 fingerprinting & Redis NX lock
│   │       ├── github_client.py     # Async HTTPX GitHub REST API client
│   │       ├── incident_service.py  # Ingestion, ARQ enqueueing, queries
│   │       └── approval_service.py  # In-memory unified diff applier & PR workflow
│   ├── worker/                      # Background worker & AI orchestrator
│   │   ├── worker.py                # ARQ entrypoint (process_incident)
│   │   ├── graph/
│   │   │   ├── state.py             # TypedDict AgentState
│   │   │   ├── nodes.py             # triage, retrieve, patch, sandbox nodes
│   │   │   └── workflow.py          # Compiled LangGraph cyclic StateGraph
│   │   └── sandbox/
│   │       └── docker_runner.py     # Air-gapped Docker container runner
│   └── web/                         # Next.js 14 TypeScript HITL dashboard
│       ├── public/
│       │   ├── banner.png
│       │   └── logo.png
│       └── src/
│           ├── app/                 # App Router pages & layout
│           ├── components/          # CommandCenter, DiffViewer, TraceTimeline, etc.
│           ├── lib/                 # Typed API client & unified diff parser
│           └── types/               # Shared TypeScript interfaces
├── packages/
│   └── core/
│       ├── ast_chunker.py           # Tree-sitter Python function/class extractor
│       └── guardrails.py            # Blast-radius, path, and unified diff validator
├── demo_target/                     # Target Python module with intentional bugs
│   ├── billing.py
│   └── test_billing.py
├── scripts/
│   ├── preflight_check.py           # Connectivity verifier (Docker, Redis, DB, Gemini)
│   └── simulate_incident.py         # E2E incident payload sender & status poller
├── evals/
│   ├── dataset/cases.py             # 15 synthetic Python bug benchmark cases
│   └── run_eval.py                  # Benchmark runner outputting Markdown scorecard
└── tests/                           # 30 unit & integration tests (API, Core, Worker, Evals)
```

---

## Local Setup & Quickstart (Zero-Cost Stack)

### Prerequisites
- **Python 3.11+** (`uv` recommended)
- **Node.js 20+** and `npm`
- **Docker Desktop** (daemon running locally)
- **Supabase Project** (Free Tier PostgreSQL)
- **Redis Cloud** (`redis://`) or **Upstash** (`rediss://`) Free Tier instance
- **Google AI Studio API Key** (`GEMINI_API_KEY`) and **GitHub Personal Access Token** (`GITHUB_TOKEN` with `Contents: Read & Write` and `Pull requests: Read & Write`)

### 1. Environment Configuration
Copy `.env.example` to `.env` and populate your credentials:
```powershell
Copy-Item .env.example .env
```

Required variables in `.env`:
```ini
# Use the Supabase IPv4 Transaction Pooler URL (port 6543) with postgresql+asyncpg://
DATABASE_URL=postgresql+asyncpg://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
REDIS_URL=redis://default:[password]@[host]:[port]
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-3.1-flash-lite
GROQ_API_KEY=gsk_...
PRIMARY_LLM_PROVIDER=gemini
SANDBOX_IMAGE=patchwork-sandbox:latest
GITHUB_TOKEN=github_pat_...
WEBHOOK_SECRET=change-this-to-a-random-hex-string
MAX_AGENT_RETRIES=3
MAX_FILES_PER_PATCH=3
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Database Schema Initialization
Execute the contents of `migrations/001_init.sql` in the **Supabase SQL Editor** to enable `vector` and `uuid-ossp` extensions, create the `incident_status` enum, and initialize the `incidents`, `agent_traces`, and `code_chunks` tables.

### 3. Install Dependencies & Build Sandbox Image
```powershell
# Create Python virtual environment and install API + Worker packages
uv venv .venv
uv pip install --python .venv\Scripts\python.exe -r apps\api\requirements.txt -r apps\worker\requirements.txt ruff pytest pytest-asyncio

# Install Next.js frontend dependencies
Push-Location apps\web; npm install; Pop-Location

# Build the isolated Docker test runner image
docker build -t patchwork-sandbox:latest -f Dockerfile.sandbox .
```

### 4. Run Preflight Telemetry Check
Verify connectivity across Docker, Redis Cloud, Supabase, and Gemini API before starting the services:
```powershell
.venv\Scripts\python.exe scripts\preflight_check.py
```
Expected output:
```text
=== Patchwork Preflight Check ===
[PASS] Docker Sandbox: Docker daemon OK, image 'patchwork-sandbox:latest' ready
[PASS] Redis: Redis OK (non-TLS (redis), <host>:<port>)
[PASS] Supabase/Postgres: PostgreSQL / Supabase OK
[PASS] Gemini API: Gemini API OK
```

### 5. Start the 3 Services
Run each process in a dedicated terminal from the repository root:

```powershell
# Terminal 1 — FastAPI Ingestion & HITL API (http://localhost:8000)
.venv\Scripts\uvicorn.exe apps.api.main:app --reload --port 8000

# Terminal 2 — ARQ Background Worker & LangGraph Engine
.venv\Scripts\arq.exe apps.worker.worker.WorkerSettings

# Terminal 3 — Next.js HITL Dashboard (http://localhost:3000)
Push-Location apps\web; npm run dev; Pop-Location
```

### 6. Trigger an End-to-End Incident Simulation
Send a simulated `ZeroDivisionError` targeting `demo_target/billing.py` and poll its state transitions:
```powershell
.venv\Scripts\python.exe scripts\simulate_incident.py --repo-owner ggerrio --repo-name Patchwork
```
Open `http://localhost:3000` to inspect the generated unified diff, review the Docker `pytest` output under **Agent Trace & Sandbox**, and click **Approve & Open PR** to create a branch (`patchwork/fix-{incident_id}`) and open a Pull Request on GitHub.

---

## Evaluation & Benchmark (`evals/`)

`evals/run_eval.py` executes the compiled LangGraph pipeline across 15 self-contained Python bug scenarios (`evals/dataset/cases.py`).

Run the benchmark suite:
```powershell
# Offline harness (local pytest runner + reference patch verification)
.venv\Scripts\python.exe -m evals.run_eval --mode local

# Live harness (Docker sandbox container + live Gemini/Groq API)
.venv\Scripts\python.exe -m evals.run_eval --mode live
```

### Measured Benchmark Results

The table below records actual execution metrics from `evals/run_eval.py --mode local` (15/15 cases resolved, average latency `1643.7 ms`) alongside the live end-to-end multi-bug run on `demo_target/billing.py` (`gemini-3.1-flash-lite` + `patchwork-sandbox:latest` Docker container):

| Scenario / Bug Category | Case ID | Resolution Status | Iterations | Sandbox Latency | Est. Token Cost |
| :--- | :--- | :--- | ---: | ---: | ---: |
| Missing dict key (`KeyError`) | `case_01_key_error` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,885 ms | 250 tok (local) |
| Empty sequence division (`ZeroDivisionError`) | `case_02_zero_division` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,613 ms | 250 tok (local) |
| Off-by-one slice bounds (`AssertionError`) | `case_03_off_by_one` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,603 ms | 250 tok (local) |
| Unawaited coroutine (`TypeError`) | `case_04_missing_await` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,671 ms | 250 tok (local) |
| String/int concatenation (`TypeError`) | `case_05_type_mismatch` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,585 ms | 250 tok (local) |
| Unchecked `None` header (`AttributeError`) | `case_06_none_attribute` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,595 ms | 250 tok (local) |
| Empty port string parse (`ValueError`) | `case_07_value_error_int` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,644 ms | 250 tok (local) |
| Mutable default argument state leak | `case_08_mutable_default` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,685 ms | 250 tok (local) |
| Malformed webhook body (`JSONDecodeError`) | `case_09_json_decode` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,588 ms | 250 tok (local) |
| Naive vs. UTC-aware datetime (`TypeError`) | `case_10_date_timezone` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,618 ms | 250 tok (local) |
| Unmatched regex `.group(1)` (`AttributeError`) | `case_11_regex_none_group` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,622 ms | 250 tok (local) |
| Dict mutation during iteration (`RuntimeError`) | `case_12_dict_iteration_mutation` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,613 ms | 250 tok (local) |
| `PurePosixPath` join with `None` (`TypeError`) | `case_13_path_join_none` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,694 ms | 250 tok (local) |
| IEEE-754 float cents rounding (`AssertionError`) | `case_14_float_precision` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,650 ms | 250 tok (local) |
| Missing recursion base case (`RecursionError`) | `case_15_recursion_base_case` | `PASS` (`AWAITING_APPROVAL`) | 1 (0 retries) | 1,590 ms | 250 tok (local) |
| **Live E2E Multi-Bug (`demo_target/billing.py`)** | `simulate_incident.py` | `PASS` (`AWAITING_APPROVAL`) | 2 (1 retry) | 4,643 ms | 1,922 tok (Gemini) |
