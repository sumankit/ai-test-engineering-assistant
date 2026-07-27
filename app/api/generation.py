from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timezone

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, HTTPException, Response

from app.graph.workflow import get_workflow
from app.parsing.docling_parser import parse_document
from app.parsing.requirement_extractor import extract_requirements
from app.schemas.schemas import GenerateRequest, JobSummary
from app.tools.export_tool import to_markdown, to_csv
from app.db.mongo import mongodb_tool
from app.db.sql import sql_db_tool
from app.storage.supabase_storage import supabase_tool
from app.tools.validation_tool import validate_requirements


router = APIRouter(tags=["generation"])


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------

@router.post("/generate")
def generate(req: GenerateRequest):
    """
    Run the LangGraph multi-agent workflow on a previously uploaded document.

    The Traceability/Coverage/Persistence Auditor (final graph node) saves
    results and execution logs to MongoDB automatically — this endpoint
    only orchestrates the run and returns the final JSON.
    """
    job = mongodb_tool.get_job(req.job_id)
    if not job:
        raise HTTPException(404, f"Unknown job_id '{req.job_id}'")

    existing = mongodb_tool.get_results(req.job_id)
    if existing and not req.force_regenerate:
        return {"job_id": req.job_id, "status": "completed", "cached": True, "results": existing}

    mongodb_tool.update_job_status(req.job_id, "processing")
    sql_db_tool.update_job_status(req.job_id, "processing")
    started_at = datetime.now(timezone.utc).isoformat()

    t0 = time.time()

    try:
        # ---- 1. Fetch and parse the original document ----
        content = supabase_tool.download(req.job_id, job["filename"])
        ext = os.path.splitext(job["filename"])[1]
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            parsed_text = parse_document(tmp_path)
        finally:
            os.unlink(tmp_path)

        # ---- 2. Extract and validate requirements ----
        requirements = extract_requirements(parsed_text)
        if not requirements:
            mongodb_tool.update_job_status(req.job_id, "failed")
            raise HTTPException(422, "No requirements could be extracted from this document")
        requirements = validate_requirements(requirements)

        # ---- 3. Run the LangGraph workflow ----
        # The final node (Traceability/Coverage/Persistence Auditor) saves
        # results + execution log to MongoDB and transitions status to
        # "completed". We only need to pass the context fields it and
        # other agents need.
        workflow = get_workflow()
        result_state = workflow.invoke(
            {
                "job_id":             req.job_id,
                "storage_url":        job.get("storage_url", ""),
                "parsed_text":        parsed_text,
                "requirements":       requirements,
                "execution_metadata": {"started_at": started_at},
            },
            config={"configurable": {"thread_id": req.job_id}},
        )

        duration = round(time.time() - t0, 3)
        return {
            "job_id":            req.job_id,
            "status":            "completed",
            "cached":            False,
            "duration_seconds":  duration,
            "results":           result_state.get("final_json", {}),
            "validation_notes":  result_state.get("validation_notes", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        # The final node never ran — update status manually.
        mongodb_tool.update_job_status(req.job_id, "failed")
        raise HTTPException(500, f"Generation failed: {e}")


# ---------------------------------------------------------------------------
# GET /jobs, GET /jobs/{job_id}
# ---------------------------------------------------------------------------

@router.get("/jobs", response_model=list[JobSummary])
def list_jobs():
    jobs = mongodb_tool.list_jobs()
    out = []
    for j in jobs:
        job_id = j.get("job_id")
        if not job_id:
            continue
        results = mongodb_tool.get_results(job_id)
        cov = (results or {}).get("coverage", {})
        out.append(JobSummary(
            job_id=job_id,
            filename=j.get("filename", "unknown"),
            status=j.get("status", "unknown"),
            created_at=j.get("created_at", ""),
            updated_at=j.get("updated_at", ""),
            coverage_percent=cov.get("coverage_percent"),
            requirement_count=len((results or {}).get("requirements", [])) or None,
        ))
    return out


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = mongodb_tool.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Unknown job_id '{job_id}'")
    results = mongodb_tool.get_results(job_id)
    log = mongodb_tool.get_execution_log(job_id)
    return {"job": job, "results": results, "execution_log": log}


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/download  (unified: ?fmt=json|markdown|csv)
# GET /json/{job_id}           (dedicated JSON route)
# GET /markdown/{job_id}       (dedicated Markdown route)
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/download")
def download_job(job_id: str, fmt: str = "json"):
    results = mongodb_tool.get_results(job_id)
    if not results:
        raise HTTPException(404, f"No results yet for job '{job_id}'. Run /generate first.")

    if fmt == "json":
        import json
        return Response(
            content=json.dumps(results, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={job_id}.json"},
        )
    if fmt == "markdown":
        md = results.get("markdown_report") or to_markdown(results)
        return Response(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={job_id}.md"},
        )
    if fmt == "csv":
        return Response(
            content=to_csv(results),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={job_id}.csv"},
        )
    raise HTTPException(400, "fmt must be one of: json, markdown, csv")


@router.get("/json/{job_id}")
def get_json(job_id: str):
    """Return the structured JSON output for a completed analysis."""
    results = mongodb_tool.get_results(job_id)
    if not results:
        raise HTTPException(404, f"No results for job '{job_id}'. Run /generate first.")
    import json
    return Response(
        content=json.dumps(results, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"inline; filename={job_id}.json"},
    )


@router.get("/markdown/{job_id}")
def get_markdown(job_id: str):
    """Return the Markdown report for a completed analysis."""
    results = mongodb_tool.get_results(job_id)
    if not results:
        raise HTTPException(404, f"No results for job '{job_id}'. Run /generate first.")
    md = results.get("markdown_report") or to_markdown(results)
    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f"inline; filename={job_id}.md"},
    )


# ---------------------------------------------------------------------------
# DELETE /jobs/{job_id}
# ---------------------------------------------------------------------------

@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    job = mongodb_tool.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Unknown job_id '{job_id}'")
    try:
        supabase_tool.delete(job_id, job["filename"])
    except Exception:
        pass
    mongodb_tool.delete_job(job_id)
    return {"job_id": job_id, "deleted": True}
