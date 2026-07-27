# Prompts

Each agent that calls an LLM directly has its own versioned prompt file
under `app/prompts/`, so a single prompt can be reviewed, diffed, or
tuned without touching orchestration code or any other agent's prompt.
`app/prompts/prompts.py` re-exports all of them under their original
constant names (`REQUIREMENT_ANALYZER`, `SCENARIO_GENERATOR`, …) so no
agent's import statement had to change when the prompts were split.

| Agent | File | Constant | Version |
|---|---|---|---|
| Requirement Analyzer | `requirement_analyzer_prompt.py` | `REQUIREMENT_ANALYZER` | v1 |
| Scenario Generator | `scenario_prompt.py` | `SCENARIO_GENERATOR` | v1 |
| Test Case Generator | `testcase_prompt.py` | `TEST_CASE_GENERATOR` | v1 |
| Boundary & Negative | `boundary_negative_prompt.py` | `BOUNDARY_NEGATIVE` | v1 |
| Edge Case | `edge_case_prompt.py` | `EDGE_CASE` | v1 |
| Acceptance Criteria | `acceptance_criteria_prompt.py` | `ACCEPTANCE_CRITERIA` | v1 |

(Traceability & Coverage, JSON Formatter, and Persistence don't call an
LLM — see `docs/agents.md` — so they have no prompt file.)

## Conventions

- Every prompt ends with an explicit output-format instruction
  ("Respond with ONLY a JSON object/array...") because the downstream
  agent parses the response as JSON (`app/agents/base.py::parse_json`,
  `app/llm/client.py::invoke_json`) and needs a predictable shape to
  parse — this is the single biggest lever for reducing malformed-JSON
  retries in practice.
- Prompts are intentionally short and single-purpose, matching each
  agent's single responsibility — this is what makes each one
  independently testable/tunable rather than one long prompt with
  conditional sections.
- Bump the `VERSION` string in a prompt file when you materially change
  its instructions, so a reviewer diffing behavior across a run can tell
  whether an output change came from a prompt edit.

## Self-repair retry

`app/llm/client.py::invoke_json()` gives the four non-tool-calling
agents (Scenario, Test Case, Edge Case, Acceptance Criteria) one
automatic retry: if the first response doesn't parse as JSON, a
follow-up turn is sent asking the model to resend ONLY corrected JSON,
before falling back to a safe default. See `docs/tools.md` for the full
retry/error-handling philosophy.
