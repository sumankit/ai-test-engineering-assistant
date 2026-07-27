"""
Agent 3 — Traceability, Coverage & Persistence Auditor Agent
--------------------------------------------------------------
Responsibilities:
  1. Build requirement -> scenario -> test-case traceability matrix.
  2. Compute coverage statistics and perform independent `compute_coverage` cross-check.
  3. Assemble structured final JSON payload via `assemble_final_json`.
  4. Auto-fix schema issues via `validate_output`.
  5. Render human-readable Markdown report via `to_markdown`.
  6. Dual-persist completed outputs and execution logs across MongoDB Atlas AND SQLAlchemy ORM.
"""
from __future__ import annotations
from datetime import datetime, timezone

from app.agents.base import BaseAgent, timed
from app.graph.state import GraphState
from app.tools.coverage_tool import compute_coverage, build_traceability_and_coverage
from app.tools.json_formatter_tool import assemble_final_json
from app.tools.validation_tool import validate_output
from app.tools.export_tool import to_markdown
from app.db.mongo import mongodb_tool
from app.db.sql import sql_db_tool


class TraceabilityCoverageAuditorAgent(BaseAgent):
    """
    Consolidated Agent 3: Computes traceability matrix, coverage metrics,
    validates output structure, formats final JSON/Markdown reports, and
    saves all state into MongoDB Atlas and SQLAlchemy relational tables.
    """

    def run(self, state: GraphState) -> dict:
        updates: dict = {}
        job_id = state.get("job_id", "")

        with timed("traceability_and_coverage", updates):
            # 1. Lookups for scenarios and test cases
            scenario_by_req: dict[str, list[str]] = {}
            for sc in state.get("scenarios", []):
                scenario_by_req.setdefault(sc.req_id, []).append(sc.scenario_id)

            testcase_by_req: dict[str, list[str]] = {}
            for tc in state.get("test_cases", []):
                testcase_by_req.setdefault(tc.req_id, []).append(tc.test_id)

            priority_by_req = {
                rid: a.get("priority", "Medium")
                for rid, a in state.get("analysis_by_req", {}).items()
            }

            # 2. Build traceability matrix & coverage summary
            rows, summary = build_traceability_and_coverage(
                state.get("requirements", []),
                scenario_by_req,
                testcase_by_req,
                priority_by_req,
            )

            # 3. Independent coverage tool cross-check
            tool_check = compute_coverage.invoke(
                {
                    "requirement_ids": [r.req_id for r in state.get("requirements", [])],
                    "covered_requirement_ids": [
                        rid for rid, ids in testcase_by_req.items() if ids
                    ],
                }
            )
            updates.setdefault("errors", [])
            if f"coverage_percent={summary.coverage_percent}" not in tool_check:
                updates["errors"].append(f"coverage cross-check mismatch: {tool_check}")

            # 4. Assemble final JSON payload & validate
            payload = assemble_final_json(
                job_id=job_id,
                requirements=state.get("requirements", []),
                scenarios=state.get("scenarios", []),
                test_cases=state.get("test_cases", []),
                acceptance_criteria=state.get("acceptance_criteria", []),
                traceability=rows,
                coverage=summary,
            )
            fixed_payload, notes = validate_output(payload)
            markdown = to_markdown(fixed_payload)

            # 5. Dual Multi-Database Persistence (MongoDB Atlas + SQLAlchemy Relational DB)
            completed_at = datetime.now(timezone.utc).isoformat()
            exec_meta = state.get("execution_metadata") or {}
            results_payload = {
                **fixed_payload,
                "markdown_report": markdown,
            }

            # Save MongoDB Atlas results & execution log
            try:
                mongodb_tool.save_results(job_id, results_payload)
                mongodb_tool.save_execution_log(
                    job_id,
                    {
                        "started_at": exec_meta.get("started_at", ""),
                        "completed_at": completed_at,
                        "node_timings": state.get("node_timings", []),
                        "errors": updates.get("errors", []),
                        "validation_notes": notes,
                    },
                )
                mongodb_tool.update_job_status(job_id, "completed")
            except Exception as exc:
                updates["errors"].append(f"mongo_persistence_error: {exc}")

            # Save SQLAlchemy relational DB records & log
            try:
                sql_db_tool.save_results(job_id, fixed_payload)
                sql_db_tool.save_execution_log(
                    job_id,
                    {
                        "started_at": exec_meta.get("started_at", ""),
                        "completed_at": completed_at,
                        "node_timings": state.get("node_timings", []),
                        "errors": updates.get("errors", []),
                        "validation_notes": notes,
                    },
                )
                sql_db_tool.update_job_status(job_id, "completed", summary.coverage_percent)
            except Exception as exc:
                updates["errors"].append(f"sql_persistence_error: {exc}")

        updates["traceability"] = rows
        updates["coverage"] = summary
        updates["final_json"] = fixed_payload
        updates["validation_notes"] = notes
        updates["markdown_report"] = markdown
        return updates
