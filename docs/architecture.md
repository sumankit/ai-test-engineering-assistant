# Architecture

One-page map of the system. For the full decision narrative, see `docs/approach.md`. For the LangGraph topology specifically, see `docs/workflow.md`.

## Component Diagram

```
                               ┌──────────────────────┐
                               │        Client         │
                               └──────────┬────────────┘
                                          │ HTTP
                               ┌──────────▼────────────┐
                               │   FastAPI (app/main.py) │
                               │   app/api/documents.py  │  POST /upload
                               │   app/api/generation.py │  POST /generate, GET/DELETE /jobs
                               └──────────┬────────────┘
                  ┌───────────────────────┼─────────────────────────┐
                  │                       │                         │
      ┌───────────▼───────────┐ ┌─────────▼───────────┐ ┌───────────▼────────────┐
      │  app/storage/          │ │  app/parsing/        │ │  app/db/                 │
      │  supabase_storage.py   │ │  docling_parser.py    │ │  mongo.py & sql.py       │
      │  (original file bytes) │ │  (Docling parser)    │ │  (MongoDB + SQLAlchemy)  │
      └────────────────────────┘ └────────┬───────────┘ └──────────────────────────┘
                                          │
                               ┌──────────▼────────────┐
                               │  app/graph/workflow.py │   LangGraph StateGraph
                               │  app/graph/state.py    │   + MemorySaver Checkpointer
                               └──────────┬────────────┘
                                          │
                   ┌──────────────────────┴───────────────────────────┐
                   │  app/agents/ (Max 3 Streamlined Agent Nodes)    │
                   │  - Requirement & Scenario Analyzer (Agent 1)     │
                   │  - Test Case Design & Synthesis (Agent 2)        │
                   │  - Traceability, Coverage & Persistence (Agent 3)│
                   └──────────────────────┬───────────────────────────┘
                                          │
                               ┌──────────▼────────────┐
                               │  stdlib logging        │  Node timers & execution logs
                               │  LangSmith Tracing    │  LANGSMITH_TRACING=true
                               └───────────────────────┘
```

## Package Layout

```
app/
├── main.py, config.py         FastAPI app bootstrap + centralized settings
├── api/                       HTTP endpoints layer (upload, generate, jobs, downloads)
├── graph/                     LangGraph topology (3 agents) + GraphState + MemorySaver checkpointer
│   ├── workflow.py            StateGraph topology with MemorySaver
│   └── state.py               GraphState TypedDict
├── agents/                    Max 3 Streamlined Agent Nodes
│   ├── base.py                BaseAgent contract + timing/json helpers
│   ├── requirement_scenario_agent.py          Agent 1: Ingestion, Requirements, Scenarios, AC
│   ├── test_case_generator_agent.py           Agent 2: Positive, Negative, Boundary & Edge Cases
│   └── traceability_coverage_auditor_agent.py Agent 3: Matrix, Coverage, JSON & Multi-DB Persistence
├── llm/                       LLM provider factory (mock | groq | gemini) + tool calling
├── prompts/                   Versioned prompt templates per agent
├── tools/                     Reusable tools (boundary, coverage, search, validation, export)
├── db/                        Persistence backends
│   ├── mongo.py               MongoDB Atlas client (uploads, results, execution_logs)
│   └── sql.py                 SQLAlchemy ORM (SQLite / Supabase Postgres relational tables)
├── storage/                   Supabase Storage (original requirement document storage)
├── parsing/                   Docling layout parser + deterministic extractor
└── schemas/                   Pydantic data models
```

## Database Persistence Strategy

The application employs a triple-persistence architecture:
1. **Supabase Storage**: Original requirement documents (PDF/DOCX/MD).
2. **MongoDB Atlas**: Unstructured job documents, output JSON artifacts, and graph node execution logs.
3. **SQLAlchemy ORM**: Relational tables (`job_runs`, `requirements`, `test_scenarios`, `test_cases`, `traceability_links`, `execution_logs`) supporting SQLite and PostgreSQL.
