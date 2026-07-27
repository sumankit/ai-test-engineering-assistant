"""
Builds the LangGraph StateGraph that orchestrates the 3-agent pipeline.

Execution topology (Max 3-Agent Pipeline)
------------------------------------------

  requirement_scenario       (Agent 1: Requirement Analysis & Scenario Generation)
              │
  test_case_generator        (Agent 2: Test Case Design [Positive, Negative, Boundary, Edge] & Test Data)
              │
  traceability_and_coverage  (Agent 3: Traceability Matrix, Coverage Summary, Validation, Exports & Multi-DB Persistence)
              │
             END

LangGraph Memory (Checkpointer)
-------------------------------
`MemorySaver` is compiled into the StateGraph to provide thread-based state checkpointing
across execution turns (keyed by job_id/thread_id).
"""
from __future__ import annotations

# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END
# pyrefly: ignore [missing-import]
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import GraphState
from app.agents.requirement_scenario_agent import RequirementScenarioAgent
from app.agents.test_case_generator_agent import TestCaseGeneratorAgent
from app.agents.traceability_coverage_auditor_agent import TraceabilityCoverageAuditorAgent


def build_workflow():
    graph = StateGraph(GraphState)

    # ---- Nodes (Max 3 Agents with Perfect Logic) ----
    graph.add_node("requirement_scenario",      RequirementScenarioAgent())
    graph.add_node("test_case_generator",       TestCaseGeneratorAgent())
    graph.add_node("traceability_and_coverage", TraceabilityCoverageAuditorAgent())

    # ---- Linear Execution Edges ----
    graph.set_entry_point("requirement_scenario")
    graph.add_edge("requirement_scenario",      "test_case_generator")
    graph.add_edge("test_case_generator",       "traceability_and_coverage")
    graph.add_edge("traceability_and_coverage", END)

    # ---- LangGraph Memory Checkpointer ----
    memory = MemorySaver()

    return graph.compile(checkpointer=memory)


_compiled_workflow = None


def get_workflow():
    global _compiled_workflow
    if _compiled_workflow is None:
        _compiled_workflow = build_workflow()
    return _compiled_workflow
