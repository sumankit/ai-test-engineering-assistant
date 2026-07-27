# Workflow (LangGraph 3-Agent Topology)

Defined in `app/graph/workflow.py`. See `docs/agents.md` for individual node details.

```
                         START
                           │
             requirement_scenario (Agent 1: Ingestion, Requirements, Scenarios, Acceptance Criteria)
                           │
             test_case_generator  (Agent 2: Positive, Negative, Boundary Value & Edge Test Cases)
                           │
         traceability_and_coverage (Agent 3: Matrix, Coverage, JSON Schema Validation & Dual DB Persistence)
                           │
                          END
```

---

## State Management & Memory Checkpointing

1. **State Reducers (`app/graph/state.py`)**:
   - `test_cases` is typed `Annotated[list[TestCase], operator.add]`. State updates append seamlessly.
   - `node_timings`, `errors`, and `validation_notes` are also list-concatenated via `operator.add`.
   - Single-writer fields (`requirements`, `scenarios`, `traceability`, `coverage`, `final_json`, `markdown_report`) update deterministically.

2. **LangGraph Memory Checkpointer**:
   - `MemorySaver` checkpointer compiles with the graph state machine:
     ```python
     memory = MemorySaver()
     compiled_workflow = graph.compile(checkpointer=memory)
     ```
   - Passed `thread_id` (keyed to `job_id`) preserves execution memory across graph turns.

---

## Dual Database Persistence

In Agent 3 (`traceability_and_coverage`), state & execution logs are committed to:
1. **MongoDB Atlas**: Document storage for job metadata (`uploads`), graph payload results (`results`), and execution node timings (`execution_logs`).
2. **SQLAlchemy ORM**: Relational tables (`job_runs`, `requirements`, `test_scenarios`, `test_cases`, `traceability_links`, `execution_logs`) supporting SQLite & PostgreSQL backends.
