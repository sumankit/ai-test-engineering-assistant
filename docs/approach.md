# Approach, Architecture, and Decision Log

## 1. What this is

An AI-powered backend that takes a software requirements document (PDF /
DOCX / Markdown) and produces test scenarios, positive/negative/boundary/
edge test cases, acceptance criteria, requirement-to-test traceability,
coverage summary, and structured JSON — via a **LangGraph multi-agent
workflow**, with **Supabase** (original file storage) and **MongoDB
Atlas** (job state, results, execution logs) as the two persistence
tools every job passes through.

## 2. Why a multi-agent pipeline instead of one big prompt

One LLM call given "generate all QA artifacts for this document" has to
simultaneously play analyst, scenario writer, boundary-value mathematician,
adversarial tester, and JSON formatter. In practice that produces
shallower output and is nearly impossible to debug ("why is coverage
80% instead of 100%?") or modify live ("swap out just the edge-case
logic"). Splitting into focused agents, each owning a related group of
responsibilities, means:

- each agent's prompt is short, focused, and independently testable
- a bad output from one agent (e.g. malformed JSON) doesn't require
  regenerating the whole report — only that node re-runs
- adding/removing/replacing an agent (an explicit review scenario) is a
  one-node change in `graph/workflow.py`, not a rewrite

## 3. Pipeline

```
Upload (FastAPI) -> Supabase Storage (original file) + MongoDB Atlas + SQLAlchemy DB (job record)
        |
Generate (FastAPI) -> Docling parse -> Requirement Extraction (deterministic)
        -> Requirement Validation (ambiguity & duplicate detection)
        -> LangGraph workflow (with MemorySaver checkpointer):
             1. Requirement & Scenario Analyzer Agent (Agent 1)
             2. Test Case Design & Synthesis Agent   (Agent 2)
             3. Traceability, Coverage & Persistence Auditor Agent (Agent 3)
        -> MongoDB Atlas + SQLAlchemy Relational DB (results + execution_logs)
        -> On-demand export (Markdown / CSV / JSON), no further AI calls
```


Every node's duration is recorded into `execution_logs.node_timings`,
and each node also logs its start/finish via a namespaced stdlib
`logging.getLogger(__name__)`, configured once at app startup
(`app/main.py`), so pipeline progress is visible without LangSmith open.
LangSmith tracing
(when `LANGSMITH_TRACING=true`) captures the same timeline plus
prompts/responses/token counts per node for the "explain your LangSmith
traces" review requirement. Malformed LLM JSON is retried once with a
self-repair prompt (`app/llm/client.py::invoke_json`) before falling
back to a safe default — see `docs/tools.md`.

## 4. Decision log

**D1 — Local fallback behind the same interface as Supabase/MongoDB Atlas.**
Both `SupabaseStorageTool` and `MongoDBAtlasTool` check for credentials
at construction time; if absent, they transparently use local disk / a
local JSON file instead, behind identical method signatures
(`upload/download/delete`, `create_job/save_results/...`). The graded,
intended backend is the cloud one — this is purely so the app is
demoable and testable without live cloud credentials in the room. If
asked live: "point `MONGODB_URI` / `SUPABASE_URL` at real instances and
nothing else in the codebase changes."

**D2 — Not every agent runs an LLM tool-calling loop.**
"Agents must have tool use" is satisfied two ways, deliberately:
- Requirement Analyzer, Boundary & Negative, and Coverage cross-check
  bind real tools (`search_requirements`, `extract_boundary_values`,
  `compute_coverage`) to the LLM via `bind_tools`, and the agent decides
  when to call them (see `llm/client.py:run_tool_calling_agent`).
- Traceability, JSON Formatter, and the deterministic extraction/
  validation steps call tools directly from code rather than through an
  LLM decision loop, because their job (assemble a table, validate a
  schema) is bookkeeping, not judgment — routing it through an LLM would
  add cost and non-determinism for zero benefit, and arithmetic like
  coverage percentages is something regex/counting does correctly and
  LLMs do not reliably. `traceability_coverage_node` still exercises the
  `compute_coverage` tool as an independent cross-check against its own
  bookkeeping, specifically so this is a real, inspectable tool call
  rather than a decorative one.

**D3 — Linear graph over N requirements, not one subgraph per requirement.**
Each node loops over `state["requirements"]` internally rather than the
graph having a `Send`/map-reduce branch per requirement. For a
requirement document of realistic size (tens of requirements) this is
simpler to trace in LangSmith (8 node executions per run, not 8×N) and
easier to reason about live. The map-reduce version (`langgraph.Send`) is
a natural extension if a document had hundreds of requirements needing
parallel processing — noted as a scaling tradeoff, not implemented.

**D4 — Deterministic extraction before any LLM call.**
`requirement_extractor.py` never calls an LLM. Given how structured the
sample requirement documents are (`FR-N: Title` + labeled sub-fields), a
regex-based extractor is both cheaper and more reliable than asking an
LLM to segment the document — LLMs are prone to merging/splitting
requirements inconsistently across a long document. A generic sentence-
based fallback (`shall/must/should` detection) handles documents that
don't use the FR-N convention.

**D5 — Requirement search via fuzzy keyword match, not embeddings.**
`tools/search_tool.py` uses `rapidfuzz` token-set matching over a
handful to a few dozen requirements per document. A vector store adds a
dependency, an indexing step, and non-determinism for a corpus this
small, with no accuracy benefit at this scale. Swapping in a real vector
tool (Chroma/FAISS via `langchain`) is a same-interface replacement if
documents grow large — this is flagged, not hidden, as a scaling
decision reviewers may want to push on.

**D6 — Mock LLM mode as the default.**
`LLM_PROVIDER=mock` runs every agent's logic with deterministic
stand-in generation instead of a real LLM call, so the entire pipeline
(upload → parse → 3 agents → validate → persist → export) is runnable
and testable with zero API keys, in CI or live. Switching to
`LLM_PROVIDER=groq` or `gemini` in `.env` changes nothing else — same
graph, same tools, same schema, real model reasoning.

## 5. Database design

**MongoDB Atlas**, three collections, one document per `job_id`:

| Collection | Purpose | Written by |
|---|---|---|
| `uploads` | job identity, filename, storage pointer, lifecycle status | `/upload`, status transitions in `/generate` |
| `results` | the final validated JSON (requirements, scenarios, test cases, acceptance criteria, traceability, coverage) | end of `/generate` |
| `execution_logs` | timing per node, tool cross-check errors, validation notes | end of `/generate` |

Splitting `results` from `execution_logs` means fetching a report for
display never has to pull debugging/timing data, and vice versa — each
collection has one reader use case.

**Supabase Storage** holds the original uploaded file only, keyed by
`{job_id}/{filename}`, so the audit trail ("what did the user actually
upload") survives independently of anything derived from it.

## 6. API design

```
POST   /upload              multipart file -> {job_id, status}
POST   /generate             {job_id, force_regenerate} -> runs the graph, persists, returns full JSON
GET    /jobs                 list all jobs + summary coverage
GET    /jobs/{job_id}        job record + results + execution log
GET    /jobs/{job_id}/download?fmt=json|markdown|csv
DELETE /jobs/{job_id}        removes job, results, logs, and the original file
```

Upload and generate are separate endpoints (rather than one
upload-and-run call) so a large document can be uploaded once and
regenerated (`force_regenerate=true`) after a prompt/agent change
without re-uploading — useful for the live-modification part of the
review.

## 7. Known limitations / things to push on in review

- The mock-mode agents are intentionally simple heuristics, not a
  simulation of what a real model would produce — they exist to prove
  the pipeline wiring, not the reasoning quality. Reasoning quality is
  only meaningfully assessable with `LLM_PROVIDER=groq|gemini` set.
- No authentication/authorization on the API — out of scope for the
  assignment's evaluation criteria, but would be required before any
  real deployment (JWT + per-job ownership, most naturally).
- `docling` is the preferred parser per the assignment; `pymupdf`/
  `python-docx` fallbacks exist so the app degrades gracefully rather
  than hard-failing if Docling isn't installed in a given environment,
  at the cost of losing table/layout structure on that path.
- Requirement search is keyword-based (D5) — a genuine limitation if
  requirements are worded very differently but semantically related;
  a vector-search swap is the documented next step.
