# Agents Architecture (3-Agent Topology)

Every agent subclasses `BaseAgent` (`app/agents/base.py`): one `run(state) -> dict` method, called by LangGraph via `__call__`. Each returns a partial state update that LangGraph merges into `GraphState`.

| # | Agent Node | File | Responsibility | Reads from state | Writes to state | Tool & Persistence Use |
|---|---|---|---|---|---|---|
| 1 | Requirement & Scenario Analyzer | `requirement_scenario_agent.py` | Ingestion (Docling parser), requirement extraction, feature area analysis, test scenarios, preconditions, postconditions, and acceptance criteria (Given/When/Then). | `parsed_text`, `requirements` | `requirements`, `analysis_by_req`, `scenarios`, `acceptance_criteria` | `parse_document`, `extract_requirements`, `search_requirements` |
| 2 | Test Case Design & Synthesis | `test_case_generator_agent.py` | Comprehensive test case generation across Positive, Negative, Boundary Value Analysis, Edge Case suggestions, Test Data suggestions, and Priorities (High/Med/Low). | `requirements`, `scenarios`, `analysis_by_req` | `test_cases`, `boundary_notes_by_req` | `extract_boundary_values` (`BoundaryValueTool`), `search_requirements` |
| 3 | Traceability, Coverage & Persistence Auditor | `traceability_coverage_auditor_agent.py` | Requirement-to-Test Traceability Matrix, Coverage Summary calculation, Output JSON formatting & validation, Markdown/CSV report exports, and Multi-Database persistence. | `requirements`, `scenarios`, `test_cases`, `analysis_by_req`, `job_id`, `execution_metadata` | `traceability`, `coverage`, `final_json`, `validation_notes`, `markdown_report`, `errors` | `compute_coverage`, `build_traceability_and_coverage`, `assemble_final_json`, `validate_output`, `to_markdown`, `to_csv`, `mongodb_tool` (MongoDB Atlas), `sql_db_tool` (SQLAlchemy ORM) |

---

## Agent Logic & Graph Wiring

1. **Agent 1 (`requirement_scenario`)**:
   - Parses document into structured sections using **Docling**.
   - Extracts functional/non-functional requirements with metadata, validations, and ambiguity flags.
   - Generates high-level test scenarios and Given/When/Then acceptance criteria.

2. **Agent 2 (`test_case_generator`)**:
   - Expands requirements and scenarios into concrete test cases.
   - Leverages `BoundaryValueTool` for numeric/range constraint boundary test cases.
   - Synthesizes edge cases, negative validation test cases, test data, and execution priorities.

3. **Agent 3 (`traceability_and_coverage`)**:
   - Builds requirement -> scenario -> test-case traceability matrix.
   - Cross-checks coverage metrics via `CoverageTool`.
   - Formats and validates structured JSON schema via `ValidationTool`.
   - Dual-persists state & execution logs into **MongoDB Atlas** and **SQLAlchemy ORM** tables (`job_runs`, `requirements`, `test_scenarios`, `test_cases`, `traceability_links`, `execution_logs`).

---

## LangGraph Memory Checkpointing
The workflow compiles a `MemorySaver` checkpointer:
```python
memory = MemorySaver()
workflow = graph.compile(checkpointer=memory)
```
Execution turns are checkpointed per thread (keyed by `job_id` / `thread_id`).
