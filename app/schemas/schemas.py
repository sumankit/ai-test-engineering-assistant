"""Pydantic models shared across the API, the tools, and the LangGraph state."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class Requirement(BaseModel):
    req_id: str
    title: str
    description: str
    section: Optional[str] = None
    raw_text: str
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None
    is_duplicate_of: Optional[str] = None
    role: Optional[str] = None
    type: str = "Functional"
    validations: list[str] = Field(default_factory=list)


class ScenarioItem(BaseModel):
    scenario_id: str
    req_id: str
    title: str
    category: str  # positive | negative | boundary | edge


class TestCase(BaseModel):
    test_id: str
    req_id: str
    scenario_id: str
    title: str
    type: str  # positive | negative | boundary | edge
    priority: str  # High | Medium | Low
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    test_data: list[str] = Field(default_factory=list)
    expected_result: str = ""
    postconditions: list[str] = Field(default_factory=list)


class AcceptanceCriterion(BaseModel):
    req_id: str
    given: str
    when: str
    then: str


class TraceabilityRow(BaseModel):
    req_id: str
    scenario_ids: list[str] = Field(default_factory=list)
    test_ids: list[str] = Field(default_factory=list)
    covered: bool = False


class CoverageSummary(BaseModel):
    total_requirements: int
    covered_requirements: int
    coverage_percent: float
    priority_breakdown: dict[str, int] = Field(default_factory=dict)


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    status: str
    storage_backend: str


class GenerateRequest(BaseModel):
    job_id: str
    force_regenerate: bool = False


class JobSummary(BaseModel):
    job_id: str
    filename: str
    status: str
    created_at: str
    updated_at: str
    coverage_percent: Optional[float] = None
    requirement_count: Optional[int] = None
