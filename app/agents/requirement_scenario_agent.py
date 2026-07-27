"""
Consolidated Agent 1 — Requirement & Scenario Analyzer
-------------------------------------------------------
Combines Requirement Analysis (feature area, priority, risk, dependencies)
and Scenario Title Generation (positive, negative, edge scenario titles)
into a single streamlined pass.
"""
from __future__ import annotations

from app.agents.base import BaseAgent, timed, parse_json
from app.graph.state import GraphState
from app.prompts import prompts
from app.llm.client import run_tool_calling_agent, invoke_json
from app.config import settings
from app.schemas.schemas import ScenarioItem
from app.tools.search_tool import search_requirements, set_search_context

_MOCK = settings.LLM_PROVIDER == "mock"
_RISKY_KEYWORDS = ("password", "payment", "auth", "encrypt", "phi", "security")


class RequirementScenarioAgent(BaseAgent):
    """
    Analyzes requirements and generates test scenario titles for each requirement.
    Outputs:
      • analysis_by_req: dict
      • scenarios: list[ScenarioItem]
    """

    def run(self, state: GraphState) -> dict:
        updates: dict = {}
        analysis_by_req: dict = {}
        scenarios: list[ScenarioItem] = []

        with timed("requirement_scenario", updates):
            set_search_context(state["requirements"])

            for req in state["requirements"]:
                # 1. Analyze metadata
                if _MOCK:
                    priority = (
                        "High"
                        if any(k in req.description.lower() for k in _RISKY_KEYWORDS)
                        else "Medium"
                    )
                    analysis_by_req[req.req_id] = {
                        "feature": (req.title.split()[0] if req.title else "General"),
                        "priority": priority,
                        "risk": (
                            "High business impact if this fails"
                            if priority == "High"
                            else "Moderate impact"
                        ),
                        "dependencies": "",
                    }
                else:
                    try:
                        text = run_tool_calling_agent(
                            prompts.REQUIREMENT_ANALYZER,
                            f"Requirement {req.req_id}: {req.title}\n{req.description}",
                            tools=[search_requirements],
                        )
                        analysis_by_req[req.req_id] = parse_json(
                            text,
                            {"feature": "Unknown", "priority": "Medium", "risk": "", "dependencies": ""},
                        )
                    except Exception as exc:
                        updates.setdefault("errors", []).append(
                            f"requirement_scenario_agent analysis[{req.req_id}]: {exc}"
                        )
                        analysis_by_req[req.req_id] = {
                            "feature": "Unknown",
                            "priority": "Medium",
                            "risk": "",
                            "dependencies": "",
                        }

                # 2. Generate scenario titles
                titles = self._generate_titles(req, updates)
                for i, title in enumerate(titles, start=1):
                    scenarios.append(
                        ScenarioItem(
                            scenario_id=f"SC-{req.req_id}-{i:02d}",
                            req_id=req.req_id,
                            title=str(title),
                            category=(
                                "negative"
                                if "invalid" in str(title).lower() or "wrong" in str(title).lower()
                                else "positive"
                            ),
                        )
                    )

        updates["analysis_by_req"] = analysis_by_req
        updates["scenarios"] = scenarios
        return updates

    def _generate_titles(self, req, updates: dict) -> list[str]:
        if _MOCK:
            titles = [
                f"Valid {req.title.lower()}",
                f"Invalid input for {req.title.lower()}",
            ]
            if "edge case" in req.raw_text.lower() or "Edge Case:" in req.raw_text:
                titles.append(f"Edge case per spec: {req.title.lower()}")
            return titles

        try:
            return invoke_json(
                system_prompt=prompts.SCENARIO_GENERATOR,
                user_prompt=f"Requirement {req.req_id}: {req.title}\n{req.description}",
                default=[f"Valid {req.title}", f"Invalid {req.title}"],
            )
        except Exception as exc:
            updates.setdefault("errors", []).append(f"requirement_scenario_agent scenarios[{req.req_id}]: {exc}")
            return [f"Valid {req.title}", f"Invalid {req.title}"]
