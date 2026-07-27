# Assumptions

Things assumed rather than specified, and what would change if the
assumption were wrong.

## Document format & content

- Requirement documents follow, or approximately follow, the `FR-N:
  Title` convention with labeled sub-fields (Description, Validation
  Conditions, Role-Based Conditions, Example Input, Example Output,
  Edge Case) — as both sample Telehealth documents do. Documents that
  don't use this convention fall back to a generic `shall/must/should`
  sentence extractor, which is deliberately less structured (title =
  first 60 chars, no sub-field separation).
- Requirements are written in English.
- The document describes a single system/product per upload — no
  cross-document requirement linking.
- Only *functional* requirements drive test generation; non-functional
  requirements (performance, uptime, compliance) and out-of-scope
  sections are parsed as context but not turned into functional test
  cases, since "test cases" for an NFR like "99.5% uptime" are a
  monitoring/SRE concern, not something a single test case captures.
- Images, diagrams, and embedded tables in the source document are
  ignored — only text/markdown-exported content is analyzed. (Docling
  does extract table structure when available; the fallback parsers do
  not.)

## Data & validation

- An email is only checked for basic format (`user@domain.com`) and
  uniqueness *as described in the requirement text* — the app doesn't
  independently verify email deliverability or run any real-world
  lookups.
- "Password case sensitive" and similar implicit rules are treated as
  true by default for boundary/negative test generation, since the
  requirement documents don't say otherwise.
- A requirement is considered "covered" once it has ≥1 generated test
  case linked to it — coverage doesn't currently weight by test
  *quality*, only presence.

## System behavior

- One `job_id` = one uploaded document = one generation run. Nothing in
  the schema models multi-document jobs or requirement diffs between
  document versions (e.g. comparing V1 vs V2's FR-6..FR-9 additions) —
  each upload is analyzed independently.
- `force_regenerate=true` fully replaces prior results for a job rather
  than merging/diffing against the previous run.
- No authentication/authorization layer — any caller with the `job_id`
  can read/regenerate/delete that job. Out of scope for the assessment's
  evaluation criteria, but noted as a pre-production requirement (JWT +
  per-job ownership).

## Infrastructure

- Reviewers may not have live MongoDB Atlas / Supabase credentials
  available during a review call, so both default to a local, on-disk
  equivalent behind the same interface (see `docs/tradeoffs.md`). The
  cloud backend is the one intended to be graded.
- `LLM_PROVIDER=mock` is assumed as the default runtime mode unless a
  real provider key is configured — the mock agents are deterministic
  stand-ins that exercise pipeline wiring, not a simulation of model
  reasoning quality.
