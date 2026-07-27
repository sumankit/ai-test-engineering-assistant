# API

Interactive docs are always available at `/docs` (Swagger UI) once the
app is running. This is the quick-reference version.

## `POST /upload`

Uploads a requirement document (PDF / DOCX / Markdown / plain text, ≤20MB).

```bash
curl -F "file=@data/telehealth_requirements_v1.pdf" http://localhost:8000/upload
```

```json
{"job_id": "JOB-A1B2C3D4E5", "filename": "telehealth_requirements_v1.pdf",
 "status": "uploaded", "storage_backend": "local_disk_fallback"}
```

Saves the file (Supabase Storage or local-disk fallback) and creates a
job record in MongoDB (`uploads` collection, `status=uploaded`).

## `POST /generate`

Runs the LangGraph workflow against a previously uploaded document.

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"job_id": "JOB-A1B2C3D4E5", "force_regenerate": false}'
```

Returns the full structured JSON (requirements, scenarios, test cases,
acceptance criteria, traceability, coverage) plus `validation_notes` and
`duration_seconds`. If results already exist and `force_regenerate` is
`false` (default), the cached result is returned immediately
(`"cached": true`) — no LLM calls, no re-run.

## `GET /jobs`

Lists every job with a summary (status, coverage %, requirement count).

## `GET /jobs/{job_id}`

Full detail for one job: the job record, its results, and its execution
log (node timings, tool cross-check errors, validation notes) — this is
the "show me previous runs" / state-persistence answer.

## `GET /jobs/{job_id}/download?fmt=json|markdown|csv`

Unified download endpoint. Also available as dedicated routes:
`GET /json/{job_id}` and `GET /markdown/{job_id}`.

## `DELETE /jobs/{job_id}`

Removes the job record, results, execution log, and the original file
from storage.

## `GET /health`, `GET /`

Liveness check, and a service-info endpoint that reports which backend
(cloud vs local fallback) is active for the LLM, Mongo, Supabase, and
LangSmith — useful to confirm configuration at a glance during a review.

## Design notes

- **Upload and generate are separate endpoints** (not one
  upload-and-run call) so a large document can be uploaded once and
  regenerated (`force_regenerate=true`) after a prompt/agent change
  without re-uploading — useful for the "modify the implementation
  live" part of a review.
- **No auth layer** — see `docs/assumptions.md`.
- Full request/response schemas live in `app/schemas/schemas.py` and are
  also visible at `/docs`.
