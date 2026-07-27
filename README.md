# AI Test Engineering Assistant

Generates test scenarios, test cases (positive / negative / boundary / edge), acceptance criteria, requirement-to-test traceability, test data suggestions, preconditions, postconditions, execution priorities, coverage summary, and structured JSON output from software requirement documents (PDF / DOCX / Markdown) — via a **LangGraph 3-Agent Workflow** with **LangGraph Memory**, **Docling** layout document parsing, **Supabase Storage** for raw document storage, **MongoDB Atlas** for document state & logs, **SQLAlchemy ORM** for relational test artifact database persistence, and **LangSmith** tracing.

See **`docs/approach.md`** for full architecture, decision log, database design, and API design — read this before a review. Visual flowchart lives in **`docs/flowchart.md`**. Shorter, focused docs live in `docs/`: `architecture.md`, `workflow.md`, `agents.md`, `tools.md`, `prompts.md`, `api.md`, `tradeoffs.md`, `assumptions.md`.


## Stack

- **FastAPI + Pydantic** — REST API layer (`app/api/`)
- **LangGraph** — Streamlined 3-agent workflow with `MemorySaver` checkpointer (`app/graph/workflow.py`, `app/graph/state.py`)
- **LangChain (`bind_tools`)** — tool calling for LLM agents (`app/llm/client.py`)
- **Groq / Gemini / deterministic mock** — LLM provider factory (`LLM_PROVIDER` in `.env`, `app/llm/client.py`)
- **MongoDB Atlas** — job state, results payload, execution logs (`app/db/mongo.py`)
- **Supabase Storage** — original document storage (`app/storage/supabase_storage.py`)
- **SQLAlchemy ORM** — relational tables for jobs, requirements, test scenarios, test cases, and traceability matrix (`app/db/sql.py`)
- **Docling** (preferred) with PyMuPDF/python-docx fallback — document parsing (`app/parsing/docling_parser.py`)
- **LangSmith** — workflow & tool tracing (`LANGSMITH_TRACING=true`)


## Setup

Dependencies are managed via `pyproject.toml` (no `requirements.txt`) — use either **uv** or **Poetry**:

```bash
# uv (recommended)
uv sync
cp .env.example .env

# or Poetry
poetry install
cp .env.example .env
```

Run commands via `uv run <cmd>` (e.g. `uv run uvicorn app.main:app --reload`) or `poetry run <cmd>`.

`.env` defaults to `LLM_PROVIDER=mock` and no cloud credentials, so the
whole pipeline runs and tests pass with **zero external services or API
keys**. To use the real backends:

- `LLM_PROVIDER=groq` + `GROQ_API_KEY=...` (free tier: console.groq.com),
  or `LLM_PROVIDER=gemini` + `GEMINI_API_KEY=...`
- `MONGODB_URI=mongodb+srv://...` pointing at an Atlas cluster
- `SUPABASE_URL=...` + `SUPABASE_KEY=...` + a storage bucket named per
  `SUPABASE_BUCKET` (default `requirement-documents`)
- `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY=...` to trace every node

## Run

```bash
uv run uvicorn app.main:app --reload
# or: poetry run uvicorn app.main:app --reload
```

API docs (Swagger UI): http://localhost:8000/docs
`GET /` reports which backend (cloud vs local fallback) each tool is
actually using, so it's obvious at a glance during a review.

## Run with Docker

```bash
docker build -t ai-test-engineering-assistant .
docker run -p 8000:8000 --env-file .env -v "$(pwd)/storage:/app/storage" ai-test-engineering-assistant
```

API docs (Swagger UI): http://localhost:8000/docs

## Tests

```bash
uv run pytest tests/ -v
# or: poetry run pytest tests/ -v
```

Covers: requirement extraction (FR-N style + generic fallback),
requirement/output validation, the boundary-value and coverage tools,
local-fallback persistence round-trips, and a full end-to-end LangGraph
run in mock mode (no API key needed).

## Walkthrough

```bash
# 1. Upload a requirements doc (two sample docs are in data/:
#    a v1/v2 pair for the telehealth appointment system assignment)
curl -X POST http://localhost:8000/upload \
  -F "file=@data/telehealth_requirements_v1.pdf"
# -> {"job_id": "JOB-XXXXXXXXXX", "filename": "...", "status": "uploaded", ...}

# 2. Run the multi-agent workflow
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"job_id": "JOB-XXXXXXXXXX"}'
# -> full JSON: requirements, scenarios, test_cases, acceptance_criteria,
#    traceability, coverage

# 3. List jobs / inspect one
curl http://localhost:8000/jobs
curl http://localhost:8000/jobs/JOB-XXXXXXXXXX

# 4. Export
curl "http://localhost:8000/jobs/JOB-XXXXXXXXXX/download?fmt=markdown" -o report.md
curl "http://localhost:8000/jobs/JOB-XXXXXXXXXX/download?fmt=csv" -o report.csv

# 5. Re-run after changing a prompt/agent, bypassing the cache
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"job_id": "JOB-XXXXXXXXXX", "force_regenerate": true}'

# 6. Delete
curl -X DELETE http://localhost:8000/jobs/JOB-XXXXXXXXXX
```

`data/telehealth_requirements_v2.pdf` is a v2 of the same spec with more
functional requirements added (Stripe payments, notifications,
prescriptions, waiting room) and more non-functional requirements
(HIPAA, latency) — useful as a second, larger document to demo against
live, or to show how the pipeline scales with requirement count.

## Project layout

```
app/
  main.py, config.py   FastAPI app bootstrap + centralized settings
  api/          FastAPI routers: documents (upload), generation (generate/jobs/download/delete)
  graph/        LangGraph orchestration: workflow.py (topology), state.py (shared GraphState)
  agents/       3 streamlined agent nodes + base.py (BaseAgent, timed, parse_json)
  llm/          LLM provider factory (mock/groq/gemini), tool-calling loop, JSON-retry helper
  prompts/      One versioned prompt file per agent + backward-compatible barrel
  tools/        Boundary, coverage, search, validation, export, JSON-formatter tools
  db/           mongo.py — MongoDB Atlas job state/results/execution logs (local-JSON fallback)
  storage/      supabase_storage.py — original document storage (local-disk fallback)
  parsing/      Docling-based document parser (+ fallback), deterministic requirement extractor
  schemas/      Pydantic models shared across API/graph/tools
tests/          pytest suite (extraction, validation, tools, fallback persistence, e2e graph)
docs/
  approach.md        Architecture, decision log, database/API design, known limitations
  architecture.md     One-page component/package map + request lifecycle
  workflow.md          LangGraph topology, fan-out/fan-in, parallel-safe state merging
  agents.md             Per-agent responsibility/input/output/tool-use table
  tools.md               Per-tool purpose + retry/error-handling philosophy
  prompts.md              Prompt versioning conventions
  api.md                   Endpoint reference with example requests
  tradeoffs.md              "Why X not Y" — quick answers for a live review
  assumptions.md             What's assumed vs specified, and what would change if wrong
data/           Sample requirement documents to demo against (telehealth v1/v2)
storage/        Local fallback storage (created at runtime if Mongo/Supabase are unset)
```

See `docs/architecture.md` for a diagram of how these pieces connect,
and `docs/approach.md` for the full narrative + decision log.
