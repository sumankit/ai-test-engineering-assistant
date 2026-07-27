# Tradeoffs

Short answers to the "why X and not Y" questions a reviewer is likely to
ask live. Each links to the fuller decision-log entry in
`docs/approach.md` §4 where one exists.

### Why LangGraph, not a single big prompt or a manual if/else chain?

A single prompt asking for scenarios + test cases + boundaries + edge
cases + acceptance criteria + traceability in one shot produces shallower
output and is nearly impossible to debug or modify live ("swap out just
the edge-case logic"). LangGraph gives focused, independently testable nodes,
explicit state, and native parallel fan-out/fan-in (`Send`), so adding,
removing, or replacing an agent is a one-node change, not a rewrite.
A hand-rolled orchestrator would have to reimplement exactly that state
merging and parallelism.

### Why MongoDB (Atlas), not Postgres/SQLAlchemy?

The data being persisted — job records, nested requirement/test-case
trees, execution logs — is naturally document-shaped and schema-light;
each `results` document differs slightly requirement-to-requirement
depending on what an agent actually produced. Forcing that into
normalized relational tables (jobs, requirements, test_cases,
traceability, …) adds a migration/ORM layer for a workload that has
exactly one write pattern (upsert-by-job_id) and one read pattern
(fetch-by-job_id). If a future requirement needed relational queries
across jobs (e.g. "all High-priority requirements across every job this
month"), Postgres would be the right call — it isn't needed here.

### Why Supabase Storage, not S3 directly or storing files in Mongo?

Supabase was specified by the assessment; Storage is the file-bytes
counterpart to Postgres, with a simple `upload/download/delete` API and
public URLs, and it's fully independent from the "derived data" store
(Mongo) — losing/regenerating results never touches the original file,
and vice versa. Storing file bytes in Mongo (GridFS) would couple the
two for no benefit.

### Why Groq/Gemini behind a provider factory, not hardcoded to one model?

`app/llm/client.py::get_llm()` is the only place that knows which
provider is active. Groq is fast/cheap for iterating; Gemini is a
plausible production choice; `mock` (the default) makes the whole
pipeline runnable with zero API keys. Swapping providers is a `.env`
edit — nothing in `agents/` or `graph/` changes.

### Why no vector DB / embeddings for requirement search?

`app/tools/search_tool.py` uses `rapidfuzz` fuzzy keyword matching over
a handful to a few dozen requirements per document. A vector store adds
a dependency, an indexing step, and non-determinism for a corpus this
small, with no measurable accuracy benefit at this scale. It's a
same-interface swap (`search_requirements` tool) if documents grow to
hundreds of requirements — see `docs/approach.md` D5.

### Why deterministic (regex) requirement extraction instead of an LLM call?

Given how structured the sample requirement documents are (`FR-N: Title`
+ labeled sub-fields), a regex extractor is cheaper, instant, and more
reliable than asking an LLM to segment a long document — LLMs are prone
to merging/splitting requirements inconsistently across pages. A
generic `shall/must/should`-sentence fallback handles less structured
documents. See `docs/approach.md` D4.

### Why do some agents call tools through an LLM tool-calling loop, and others call them directly?

"Agents must use tools" is satisfied two ways on purpose. Requirement
Analyzer, Boundary & Negative, and the coverage cross-check bind real
tools to the LLM and let the model *decide* when to call them — that's
judgment work. Traceability assembly, JSON formatting, and coverage
arithmetic call tools directly from code, because "count how many
requirements have ≥1 test case" is bookkeeping, not judgment — routing
deterministic arithmetic through an LLM adds cost and non-determinism
for zero benefit (LLMs are unreliable at exact counts/percentages over
long lists). See `docs/approach.md` D2.

### Why local-disk / local-JSON fallbacks instead of requiring real Mongo/Supabase credentials?

Both `MongoDBAtlasTool` and `SupabaseStorageTool` check for credentials
at construction time and transparently fall back to disk/local-JSON
behind an *identical* method signature if absent. The graded, intended
backend is the cloud one — this exists purely so the app is demoable
and testable (including in CI) without live cloud credentials in the
room. Pointing `MONGODB_URI`/`SUPABASE_URL` at real instances changes
nothing else in the codebase. See `docs/approach.md` D1.

### Why one LangGraph run per requirement-document, not a subgraph per requirement?

Each node loops over `state["requirements"]` internally rather than the
graph branching per-requirement via `Send`. For a realistic document
(tens of requirements) this is simpler to trace in LangSmith (8 node
executions per run, not 8×N) and easier to reason about live. The
map-reduce version is a natural extension for documents with hundreds of
requirements — noted as a scaling tradeoff, not implemented. See
`docs/approach.md` D3.

### Why split prompts into one file per agent instead of one prompts.py?

Each prompt can now be reviewed, diffed, and tuned independently, and
carries its own `VERSION` marker (see `docs/prompts.md`). The tradeoff
is more files for a small win at this prompt count (6); the win compounds
if the project grows more agents or starts A/B testing prompt revisions.
`app/prompts/prompts.py` re-exports everything under the original names
so no agent's import changed.
