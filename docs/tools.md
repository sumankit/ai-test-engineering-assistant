# Tools

"Tools do work; agents decide when to use it." Every tool is a small,
independently unit-testable function with one job. Tools marked
**LLM-bound** are exposed to an agent via `bind_tools` (the model decides
whether/when to call them, in real LLM mode); the rest are called
directly from agent or API code because their job is deterministic
bookkeeping, not judgment (see `docs/tradeoffs.md`).

| Tool | File | Type | Purpose |
|---|---|---|---|
| `extract_boundary_values` | `tools/boundary_tool.py` | **LLM-bound** | Regex-extracts numeric constraints (ranges, min/max, over/under) from a requirement's text and returns ready-to-use boundary values (`value-1`, `value`, `value+1` style), so the LLM/agent doesn't have to eyeball arithmetic. |
| `search_requirements` | `tools/search_tool.py` | **LLM-bound** | Fuzzy keyword search (`rapidfuzz`) over the current job's requirements, so the Requirement Analyzer can check for overlap with an already-seen requirement mid-reasoning instead of the whole list being dumped into every prompt. |
| `compute_coverage` | `tools/coverage_tool.py` | **LLM-bound** (called directly by the Traceability agent as an independent cross-check) | Deterministic coverage-percentage arithmetic given requirement ids and covered-requirement ids. |
| `build_traceability_and_coverage` | `tools/coverage_tool.py` | direct call | Assembles the requirement→scenario→test-case traceability rows and the coverage summary (priority breakdown included). |
| `assemble_final_json` | `tools/json_formatter_tool.py` | direct call | Serializes every pipeline output (requirements, scenarios, test cases, acceptance criteria, traceability, coverage) into the one final response/export shape. |
| `validate_requirements` | `tools/validation_tool.py` | direct call | Pre-flight checks run *before* any agent sees the requirements: flags vague language, duplicate/near-duplicate requirements, missing fields. |
| `validate_output` | `tools/validation_tool.py` | direct call | Post-flight checks on the assembled final JSON: auto-fixes minor schema issues, records human-readable notes surfaced in the API response. |
| `to_markdown` / `to_csv` | `tools/export_tool.py` | direct call | Pure formatting of the already-validated final JSON into Markdown / CSV — no AI calls, safe to re-run on demand for any export format. |
| `chunk_text` / `chunk_document_for_requirements` | `tools/chunker.py` | direct call (available, not currently on the hot path) | Splits long document text into overlapping chunks that fit an LLM context window without losing inter-sentence context, for documents too large to parse/extract from in one shot. |
| `mongodb_tool` | `db/mongo.py` | infra | Job state / results / execution-log persistence (MongoDB Atlas, local-JSON fallback). |
| `supabase_tool` | `storage/supabase_storage.py` | infra | Original uploaded file storage (Supabase Storage, local-disk fallback). |
| `sql_db_tool` | `db/sql.py` | infra | Relational persistence for jobs, requirements, test cases, and the traceability matrix (SQLAlchemy ORM, PostgreSQL/SQLite). |
| `run_tool_calling_agent` | `llm/client.py` | infra | Shared bind-tools + tool-call execution loop used by every LLM-bound-tool agent, so the loop isn't duplicated per agent. |
| `invoke_json` | `llm/client.py` | infra | Shared direct-LLM-call helper for agents with no tools (Scenario, Test Case, Edge Case, Acceptance Criteria); retries once with a self-repair prompt if the response isn't valid JSON before falling back to a safe default. |

## Retry / error-handling philosophy

Every tool call that can fail (parsing, an LLM call, a Mongo/Supabase
call) is wrapped so a single failure degrades gracefully instead of
crashing the graph:

- **Document parsing** — Docling failure falls back to PyMuPDF (PDF) or
  python-docx (DOCX) automatically (`parsing/docling_parser.py`).
- **Malformed LLM JSON** — `invoke_json()` retries once with an explicit
  "your last response wasn't valid JSON, resend only the corrected
  JSON" follow-up turn before falling back to a safe default (`{}`/`[]`)
  so one bad generation never breaks the run.
- **Persistence** — each of the Traceability/Coverage/Persistence
  Auditor's three writes (results, execution log, status) is wrapped
  individually; a transient Atlas hiccup after the pipeline has already
  succeeded is recorded in `state["errors"]` rather than losing the
  in-memory result.
- **Coverage** — the deterministic bookkeeping result is cross-checked
  against an independent `compute_coverage` tool call; a mismatch is
  logged as an error, not silently trusted.
