"""
Consolidated Agent 2 — Comprehensive Test Case & Acceptance Criteria Generator
---------------------------------------------------------------------------------
Generates:
  1. Base test cases from scenarios (positive & negative).
  2. Boundary & negative test cases using the `extract_boundary_values` tool.
  3. Edge case test cases covering security, unicode, payload limit & concurrency edge cases.
  4. Structured Given / When / Then Acceptance Criteria for every requirement.
"""
from __future__ import annotations

from app.agents.base import BaseAgent, timed, parse_json
from app.graph.state import GraphState
from app.prompts import prompts
from app.llm.client import invoke_json, run_tool_calling_agent
from app.config import settings
from app.schemas.schemas import TestCase, AcceptanceCriterion
from app.tools.boundary_tool import extract_boundary_values

_MOCK = settings.LLM_PROVIDER == "mock"
_NO_CONSTRAINTS_MARKER = "No explicit numeric constraints"

_EDGE_LIBRARY: list[str] = [
    "Unicode/emoji input",
    "Input at maximum field length + 1",
    "Null/empty submission",
    "Whitespace-only input",
    "SQL/HTML injection payload",
    "Simultaneous concurrent requests",
    "Clock/timezone boundary",
]


class TestCaseGeneratorAgent(BaseAgent):
    """
    Expands scenarios into full test cases (positive, negative, boundary, edge)
    and produces Given/When/Then acceptance criteria for all requirements.
    """

    def run(self, state: GraphState) -> dict:
        updates: dict = {}
        all_test_cases: list[TestCase] = []
        boundary_notes: dict = {}
        ac_list: list[AcceptanceCriterion] = []

        req_by_id = {r.req_id: r for r in state["requirements"]}
        tc_counters: dict[str, int] = {}

        with timed("test_case_generator", updates):
            analysis_map = state.get("analysis_by_req", {})

            # 1. Base Test Cases from Scenarios
            for sc in state.get("scenarios", []):
                req = req_by_id.get(sc.req_id)
                if not req:
                    continue
                body = self._generate_base_tc_body(req, sc, updates)
                tc_counters[req.req_id] = tc_counters.get(req.req_id, 0) + 1
                priority = analysis_map.get(req.req_id, {}).get("priority", "Medium")

                all_test_cases.append(
                    TestCase(
                        test_id=f"TC-{req.req_id}-{tc_counters[req.req_id]:02d}",
                        req_id=req.req_id,
                        scenario_id=sc.scenario_id,
                        title=body.get("title", sc.title),
                        type=body.get("type", "positive"),
                        priority=priority,
                        preconditions=body.get("preconditions", []),
                        steps=body.get("steps", []),
                        test_data=body.get("test_data", []),
                        expected_result=body.get("expected_result", ""),
                        postconditions=body.get("postconditions", []),
                    )
                )

            # 2. Boundary Value & Negative Cases via Boundary Tool
            for req in state["requirements"]:
                tool_result = extract_boundary_values.invoke(
                    {"requirement_text": req.raw_text}
                )
                boundary_notes[req.req_id] = tool_result

                if _NO_CONSTRAINTS_MARKER not in tool_result:
                    b_items = self._generate_boundary_items(req, tool_result, updates)
                    for item in b_items:
                        tc_counters[req.req_id] = tc_counters.get(req.req_id, 0) + 1
                        all_test_cases.append(
                            TestCase(
                                test_id=f"TC-{req.req_id}-B{tc_counters[req.req_id]:02d}",
                                req_id=req.req_id,
                                scenario_id=f"SC-{req.req_id}-BOUNDARY",
                                title=item.get("title", "Boundary case"),
                                type=item.get("type", "boundary"),
                                priority=analysis_map.get(req.req_id, {}).get("priority", "Medium"),
                                test_data=item.get("test_data", []),
                                expected_result=item.get("expected_result", ""),
                            )
                        )

            # 3. Edge Cases
            for req in state["requirements"]:
                e_items = self._generate_edge_items(req, updates)
                for item in e_items:
                    tc_counters[req.req_id] = tc_counters.get(req.req_id, 0) + 1
                    all_test_cases.append(
                        TestCase(
                            test_id=f"TC-{req.req_id}-E{tc_counters[req.req_id]:02d}",
                            req_id=req.req_id,
                            scenario_id=f"SC-{req.req_id}-EDGE",
                            title=item.get("title", "Edge case"),
                            type="edge",
                            priority=analysis_map.get(req.req_id, {}).get("priority", "Medium"),
                            test_data=item.get("test_data", []),
                            expected_result=item.get("expected_result", ""),
                        )
                    )

            # 4. Acceptance Criteria
            for req in state["requirements"]:
                ac_body = self._generate_ac_body(req, updates)
                ac_list.append(
                    AcceptanceCriterion(
                        req_id=req.req_id,
                        given=ac_body.get("given", ""),
                        when=ac_body.get("when", ""),
                        then=ac_body.get("then", ""),
                    )
                )

        updates["test_cases"] = all_test_cases
        updates["boundary_notes_by_req"] = boundary_notes
        updates["acceptance_criteria"] = ac_list
        return updates

    # --- Helpers ---
    def _generate_base_tc_body(self, req, sc, updates: dict) -> dict:
        if _MOCK:
            is_negative = sc.category == "negative"
            return {
                "title": sc.title,
                "type": "negative" if is_negative else "positive",
                "preconditions": [f"User/system state satisfies preconditions of {req.req_id}"],
                "steps": [
                    f"Set up state for {req.title}",
                    f"Execute action described in {req.req_id}",
                    "Observe system response",
                ],
                "test_data": ["Invalid/edge input" if is_negative else "Valid representative input"],
                "expected_result": (
                    "System rejects the action with the documented error"
                    if is_negative
                    else "System completes the action as described in Example Output"
                ),
                "postconditions": ["State unchanged" if is_negative else "State updated per requirement"],
            }
        try:
            return invoke_json(
                system_prompt=prompts.TEST_CASE_GENERATOR,
                user_prompt=f"Requirement: {req.title}\n{req.description}\nScenario: {sc.title}",
                default={},
            )
        except Exception as exc:
            updates.setdefault("errors", []).append(f"test_case_generator[{sc.scenario_id}]: {exc}")
            return {}

    def _generate_boundary_items(self, req, tool_result: str, updates: dict) -> list[dict]:
        if _MOCK:
            return [
                {
                    "title": f"Boundary values for {req.title}",
                    "type": "boundary",
                    "test_data": [tool_result],
                    "expected_result": (
                        "System accepts valid boundary values and rejects out-of-range values per validation rules"
                    ),
                }
            ]
        try:
            text = run_tool_calling_agent(
                prompts.BOUNDARY_NEGATIVE,
                f"Requirement {req.req_id}: {req.title}\n{req.raw_text}",
                tools=[extract_boundary_values],
            )
            return parse_json(text, [])
        except Exception as exc:
            updates.setdefault("errors", []).append(f"test_case_generator boundary[{req.req_id}]: {exc}")
            return []

    def _generate_edge_items(self, req, updates: dict) -> list[dict]:
        if _MOCK:
            text_lower = req.raw_text.lower()
            relevant = [
                e for e in _EDGE_LIBRARY
                if ("concurrent" not in e.lower() or "simultaneous" in text_lower or "same time" in text_lower)
            ]
            return [
                {
                    "title": f"{e} on {req.title}",
                    "test_data": [e],
                    "expected_result": "System handles input safely without crashing or corrupting state",
                }
                for e in relevant[:3]
            ]
        try:
            return invoke_json(
                system_prompt=prompts.EDGE_CASE,
                user_prompt=f"Requirement {req.req_id}: {req.title}\n{req.description}",
                default=[],
            )
        except Exception as exc:
            updates.setdefault("errors", []).append(f"test_case_generator edge[{req.req_id}]: {exc}")
            return []

    def _generate_ac_body(self, req, updates: dict) -> dict:
        if _MOCK:
            return {
                "given": f"the preconditions of {req.req_id} are met",
                "when": f'the user/system performs the action in "{req.title}"',
                "then": "the system behaves as described in the requirement's example output",
            }
        try:
            return invoke_json(
                system_prompt=prompts.ACCEPTANCE_CRITERIA,
                user_prompt=f"Requirement {req.req_id}: {req.title}\n{req.description}",
                default={},
            )
        except Exception as exc:
            updates.setdefault("errors", []).append(f"test_case_generator ac[{req.req_id}]: {exc}")
            return {}
