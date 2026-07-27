"""
SQLAlchemy Database Persistence Tool
-----------------------------------
Provides relational ORM persistence for job runs, requirements, test scenarios,
test cases, traceability matrix entries, and execution logs.

Supported backends: SQLite (default fallback at storage/app.db) or PostgreSQL / Supabase PG
when DATABASE_URL is configured in environment variables.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# pyrefly: ignore [missing-import]
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

from app.config import settings

Base = declarative_base()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRunModel(Base):
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), unique=True, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="uploaded")
    storage_url = Column(Text, nullable=True)
    storage_backend = Column(String(32), nullable=True)
    coverage_percent = Column(Float, nullable=True)
    created_at = Column(String(64), default=_now)
    updated_at = Column(String(64), default=_now, onupdate=_now)


class RequirementModel(Base):
    __tablename__ = "requirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    req_id = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    section = Column(String(255), nullable=True)
    raw_text = Column(Text, nullable=True)
    is_ambiguous = Column(Boolean, default=False)
    ambiguity_reason = Column(Text, nullable=True)
    is_duplicate_of = Column(String(64), nullable=True)
    role = Column(String(128), nullable=True)
    type = Column(String(64), default="Functional")
    validations_json = Column(Text, nullable=True)


class TestScenarioModel(Base):
    __tablename__ = "test_scenarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    scenario_id = Column(String(64), nullable=False)
    req_id = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False)


class TestCaseModel(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    test_id = Column(String(64), nullable=False)
    req_id = Column(String(64), nullable=False)
    scenario_id = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    type = Column(String(64), nullable=False)  # positive | negative | boundary | edge
    priority = Column(String(32), nullable=False, default="Medium")
    preconditions_json = Column(Text, nullable=True)
    steps_json = Column(Text, nullable=True)
    test_data_json = Column(Text, nullable=True)
    expected_result = Column(Text, nullable=False)
    postconditions_json = Column(Text, nullable=True)


class TraceabilityModel(Base):
    __tablename__ = "traceability_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    req_id = Column(String(64), nullable=False)
    scenario_ids_json = Column(Text, nullable=True)
    test_ids_json = Column(Text, nullable=True)
    covered = Column(Boolean, default=False)


class ExecutionLogModel(Base):
    __tablename__ = "execution_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    started_at = Column(String(64), nullable=True)
    completed_at = Column(String(64), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    log_data_json = Column(Text, nullable=True)


class SQLAlchemyDBTool:
    def __init__(self):
        db_url = settings.DATABASE_URL
        if db_url.startswith("sqlite"):
            os.makedirs(settings.LOCAL_STORAGE_DIR, exist_ok=True)
            self.engine = create_engine(db_url, connect_args={"check_same_thread": False})
        else:
            self.engine = create_engine(db_url)

        self.SessionFactory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.SessionFactory)
        self.init_db()

    def init_db(self) -> None:
        Base.metadata.create_all(bind=self.engine)

    def create_job(self, job_id: str, filename: str, storage_url: str, storage_backend: str) -> None:
        session = self.Session()
        try:
            existing = session.query(JobRunModel).filter_by(job_id=job_id).first()
            if existing:
                existing.filename = filename
                existing.storage_url = storage_url
                existing.storage_backend = storage_backend
                existing.status = "uploaded"
                existing.updated_at = _now()
            else:
                job = JobRunModel(
                    job_id=job_id,
                    filename=filename,
                    storage_url=storage_url,
                    storage_backend=storage_backend,
                    status="uploaded",
                    created_at=_now(),
                    updated_at=_now(),
                )
                session.add(job)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self.Session.remove()

    def update_job_status(self, job_id: str, status: str, coverage_percent: Optional[float] = None) -> None:
        session = self.Session()
        try:
            job = session.query(JobRunModel).filter_by(job_id=job_id).first()
            if job:
                job.status = status
                if coverage_percent is not None:
                    job.coverage_percent = coverage_percent
                job.updated_at = _now()
                session.commit()
        except Exception:
            session.rollback()
        finally:
            self.Session.remove()

    def save_results(self, job_id: str, results: Dict[str, Any]) -> None:
        session = self.Session()
        try:
            session.query(RequirementModel).filter_by(job_id=job_id).delete()
            session.query(TestScenarioModel).filter_by(job_id=job_id).delete()
            session.query(TestCaseModel).filter_by(job_id=job_id).delete()
            session.query(TraceabilityModel).filter_by(job_id=job_id).delete()

            for req in results.get("requirements", []):
                session.add(RequirementModel(
                    job_id=job_id,
                    req_id=req.get("req_id", ""),
                    title=req.get("title", ""),
                    description=req.get("description", ""),
                    section=req.get("section"),
                    raw_text=req.get("raw_text", ""),
                    is_ambiguous=req.get("is_ambiguous", False),
                    ambiguity_reason=req.get("ambiguity_reason"),
                    is_duplicate_of=req.get("is_duplicate_of"),
                    role=req.get("role"),
                    type=req.get("type", "Functional"),
                    validations_json=json.dumps(req.get("validations", [])),
                ))

            for sc in results.get("scenarios", []):
                session.add(TestScenarioModel(
                    job_id=job_id,
                    scenario_id=sc.get("scenario_id", ""),
                    req_id=sc.get("req_id", ""),
                    title=sc.get("title", ""),
                    category=sc.get("category", "positive"),
                ))

            for tc in results.get("test_cases", []):
                session.add(TestCaseModel(
                    job_id=job_id,
                    test_id=tc.get("test_id", ""),
                    req_id=tc.get("req_id", ""),
                    scenario_id=tc.get("scenario_id", ""),
                    title=tc.get("title", ""),
                    type=tc.get("type", "positive"),
                    priority=tc.get("priority", "Medium"),
                    preconditions_json=json.dumps(tc.get("preconditions", [])),
                    steps_json=json.dumps(tc.get("steps", [])),
                    test_data_json=json.dumps(tc.get("test_data", [])),
                    expected_result=tc.get("expected_result", ""),
                    postconditions_json=json.dumps(tc.get("postconditions", [])),
                ))

            for tr in results.get("traceability", []):
                session.add(TraceabilityModel(
                    job_id=job_id,
                    req_id=tr.get("req_id", ""),
                    scenario_ids_json=json.dumps(tr.get("scenario_ids", [])),
                    test_ids_json=json.dumps(tr.get("test_ids", [])),
                    covered=tr.get("covered", False),
                ))

            cov = results.get("coverage", {}).get("coverage_percent")
            job = session.query(JobRunModel).filter_by(job_id=job_id).first()
            if job:
                job.status = "completed"
                if cov is not None:
                    job.coverage_percent = float(cov)
                job.updated_at = _now()

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self.Session.remove()

    def save_execution_log(self, job_id: str, log: Dict[str, Any]) -> None:
        session = self.Session()
        try:
            log_model = ExecutionLogModel(
                job_id=job_id,
                started_at=log.get("started_at"),
                completed_at=log.get("completed_at"),
                duration_seconds=log.get("duration_seconds"),
                log_data_json=json.dumps(log),
            )
            session.add(log_model)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            self.Session.remove()

    def get_results(self, job_id: str) -> Optional[Dict[str, Any]]:
        session = self.Session()
        try:
            reqs = session.query(RequirementModel).filter_by(job_id=job_id).all()
            if not reqs:
                return None

            requirements = []
            for r in reqs:
                requirements.append({
                    "req_id": r.req_id,
                    "title": r.title,
                    "description": r.description,
                    "section": r.section,
                    "raw_text": r.raw_text,
                    "is_ambiguous": r.is_ambiguous,
                    "ambiguity_reason": r.ambiguity_reason,
                    "is_duplicate_of": r.is_duplicate_of,
                    "role": r.role,
                    "type": r.type,
                    "validations": json.loads(r.validations_json) if r.validations_json else [],
                })

            scenarios = []
            for sc in session.query(TestScenarioModel).filter_by(job_id=job_id).all():
                scenarios.append({
                    "scenario_id": sc.scenario_id,
                    "req_id": sc.req_id,
                    "title": sc.title,
                    "category": sc.category,
                })

            test_cases = []
            for tc in session.query(TestCaseModel).filter_by(job_id=job_id).all():
                test_cases.append({
                    "test_id": tc.test_id,
                    "req_id": tc.req_id,
                    "scenario_id": tc.scenario_id,
                    "title": tc.title,
                    "type": tc.type,
                    "priority": tc.priority,
                    "preconditions": json.loads(tc.preconditions_json) if tc.preconditions_json else [],
                    "steps": json.loads(tc.steps_json) if tc.steps_json else [],
                    "test_data": json.loads(tc.test_data_json) if tc.test_data_json else [],
                    "expected_result": tc.expected_result,
                    "postconditions": json.loads(tc.postconditions_json) if tc.postconditions_json else [],
                })

            traceability = []
            for tr in session.query(TraceabilityModel).filter_by(job_id=job_id).all():
                traceability.append({
                    "req_id": tr.req_id,
                    "scenario_ids": json.loads(tr.scenario_ids_json) if tr.scenario_ids_json else [],
                    "test_ids": json.loads(tr.test_ids_json) if tr.test_ids_json else [],
                    "covered": tr.covered,
                })

            return {
                "job_id": job_id,
                "requirements": requirements,
                "scenarios": scenarios,
                "test_cases": test_cases,
                "traceability": traceability,
            }
        finally:
            self.Session.remove()


sql_db_tool = SQLAlchemyDBTool()
