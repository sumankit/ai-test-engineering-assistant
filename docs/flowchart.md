Nisha# System Architecture Flowchart

This document provides a visual flowchart representation of the **AI Test Engineering Assistant** working pipeline, covering document ingestion, parsing, the 3-agent LangGraph workflow, multi-database persistence, and report generation.

---

## Complete Working Flowchart

```mermaid
flowchart TD
    subgraph ClientLayer["1. Client & REST API Layer (FastAPI)"]
        Client[QA Engineer / Client] -->|1. POST /upload - Upload Requirement Doc| UploadEP["POST /upload"]
        Client -->|2. POST /generate - Trigger Test Artifact Generation| GenEP["POST /generate"]
        Client -->|3. GET /jobs & /download - Export Artifacts| JobEP["GET /jobs /download"]
    end

    subgraph StorageIngestion["2. Ingestion & Initial Persistence"]
        UploadEP -->|Store Raw Doc PDF / DOCX / MD| SupabaseStore[("Supabase Storage\n(Original File Storage)")]
        UploadEP -->|Create Initial Job Status| MongoUploads[("MongoDB Atlas\n'uploads' Collection")]
        UploadEP -->|Create Relational Job Entry| SQLJobRuns[("SQLAlchemy Database\n'job_runs' Table")]
    end

    subgraph DocumentParsing["3. Document Parsing & Extraction"]
        GenEP -->|Fetch Raw File Bytes| SupabaseStore
        GenEP -->|Docling Ingestion Engine| DoclingParser["Docling Document Parser\n(Layout & Markdown Extractor)"]
        DoclingParser -->|Extracted Text| ReqExtractor["Requirement Extractor Tool\n(Functional & Non-Functional)"]
        ReqExtractor -->|Validation & Ambiguity Audit| ReqValidator["Validation Tool\n(Ambiguity & Duplicate Checks)"]
    end

    subgraph LangGraphWorkflow["4. LangGraph 3-Agent Execution Pipeline (with MemorySaver Checkpointer)"]
        ReqValidator -->|Initial State Injection| Agent1

        subgraph Agent1Node["Agent 1: Requirement & Scenario Analyzer"]
            Agent1["RequirementScenarioAgent"]
            Agent1 -->|Extract & Structure| ReqAnalysis["Requirement Feature & Risk Analysis"]
            Agent1 -->|Synthesize| Scenarios["Test Scenarios (Pos / Neg / Boundary / Edge)"]
            Agent1 -->|Format| AcceptanceCriteria["Acceptance Criteria (Given / When / Then)"]
        end

        Agent1Node -->|Pass GraphState| Agent2Node

        subgraph Agent2Node["Agent 2: Test Case Design & Synthesis"]
            Agent2["TestCaseGeneratorAgent"]
            Agent2 -->|Identify Numerical / Range Constraints| BoundaryTool["BoundaryValueTool\n(Equivalence Partitioning & BVA)"]
            BoundaryTool --> BoundaryCases["Boundary Value Test Cases"]
            Agent2 --> PositiveCases["Positive Test Cases"]
            Agent2 --> NegativeCases["Negative Test Cases & Invalid Inputs"]
            Agent2 --> EdgeCases["Edge Case Suggestions (Concurrency, Unicode, Limits)"]
            Agent2 --> TestData["Test Data Suggestions & Pre/Postconditions"]
            Agent2 --> Priorities["Execution Priority Assignment (High / Med / Low)"]
        end

        Agent2Node -->|Pass Consolidated Test Suite| Agent3Node

        subgraph Agent3Node["Agent 3: Traceability, Coverage & Persistence Auditor"]
            Agent3["TraceabilityCoverageAuditorAgent"]
            Agent3 --> Matrix["Build Traceability Matrix\n(Req ID → Scenario ID → Test ID)"]
            Agent3 --> CovTool["CoverageTool\n(Calculate Coverage % & Priority Breakdown)"]
            Agent3 --> ValTool["ValidationTool & JSON Formatter\n(Schema Auto-Fix & Verification)"]
            Agent3 --> ExportTool["ExportTool\n(Render Markdown & CSV Reports)"]
        end
    end

    subgraph MemoryObservability["5. Memory & Observability"]
        LangGraphWorkflow <-->|State Checkpointing per thread_id| MemorySaver["LangGraph MemorySaver"]
        LangGraphWorkflow -.->|Trace Prompts & Token Timings| LangSmith["LangSmith Tracing"]
    end

    subgraph DualDBPersistence["6. Multi-Database Persistence (Executed in Agent 3)"]
        Agent3Node -->|Persist Output Artifacts| MongoResults[("MongoDB Atlas\n'results' Collection")]
        Agent3Node -->|Persist Node Timings & Logs| MongoLogs[("MongoDB Atlas\n'execution_logs' Collection")]
        Agent3Node -->|Persist Relational Schema| SQLTables[("SQLAlchemy ORM Relational DB\n(requirements, test_scenarios, test_cases, traceability_links)")]
    end

    subgraph ArtifactOutput["7. Outputs Delivered to Client"]
        GenEP -->|Return Structured JSON Response| Client
        JobEP -->|Export Formats| OutputFormats["Structured JSON / Markdown / CSV"]
    end

    style LangGraphWorkflow fill:#1f2937,stroke:#3b82f6,stroke-width:2px,color:#fff
    style Agent1Node fill:#111827,stroke:#60a5fa,stroke-width:1px,color:#fff
    style Agent2Node fill:#111827,stroke:#34d399,stroke-width:1px,color:#fff
    style Agent3Node fill:#111827,stroke:#f59e0b,stroke-width:1px,color:#fff
    style DualDBPersistence fill:#18181b,stroke:#a855f7,stroke-width:1.5px,color:#fff
```

---

## Detailed Pipeline Stages

### Stage 1: Document Upload & Ingestion
1. Client issues `POST /upload` with a software requirement document (PDF, DOCX, Markdown).
2. The raw document content is saved into **Supabase Storage**.
3. Initial job metadata is recorded in **MongoDB Atlas** (`uploads` collection) and **SQLAlchemy DB** (`job_runs` table).

### Stage 2: Document Parsing & Validation
1. Client issues `POST /generate`.
2. **Docling Document Parser** processes the document layout into clean markdown text.
3. **Requirement Extractor Tool** parses functional and non-functional requirements.
4. **Validation Tool** audits requirements for ambiguity flags and duplicate entries.

### Stage 3: LangGraph 3-Agent Execution Pipeline
- **Agent 1 (`RequirementScenarioAgent`)**:
  Generates requirement risk analysis, high-level test scenarios (Positive, Negative, Boundary, Edge), and Given/When/Then acceptance criteria.
- **Agent 2 (`TestCaseGeneratorAgent`)**:
  Calls `BoundaryValueTool` for boundary analysis on numeric range constraints, generates full test cases (steps, expected results, test data, preconditions, postconditions, and High/Med/Low execution priorities).
- **Agent 3 (`TraceabilityCoverageAuditorAgent`)**:
  Builds Requirement-to-Test Traceability Matrix, computes coverage metrics via `CoverageTool`, auto-validates JSON payload via `ValidationTool`, renders Markdown/CSV reports via `ExportTool`, and saves data into MongoDB and SQLAlchemy databases.

### Stage 4: State Checkpointing & Tracing
- **LangGraph `MemorySaver`** checkpoints the state per thread/job ID across execution turns.
- **LangSmith Tracing** captures full trace graphs, prompts, node timings, and token metrics.

### Stage 5: Multi-Database Persistence
- **MongoDB Atlas**: Stores output result JSON (`results` collection) and timing execution logs (`execution_logs` collection).
- **SQLAlchemy ORM**: Populates relational entities (`requirements`, `test_scenarios`, `test_cases`, `traceability_links`, `execution_logs`) in SQLite or Supabase PostgreSQL.
