"""
Backward-compatible prompt barrel.

Historically every agent did ``from app.prompts import prompts`` and then
``prompts.REQUIREMENT_ANALYZER``. Prompts now live one-per-file (prompt
versioning — see docs/prompts.md) so each can be reviewed, diffed, and
tuned independently. This module re-exports all of them under their
original names so no call site had to change when the prompts were split.
"""
from app.prompts.requirement_analyzer_prompt import REQUIREMENT_ANALYZER
from app.prompts.scenario_prompt import SCENARIO_GENERATOR
from app.prompts.testcase_prompt import TEST_CASE_GENERATOR
from app.prompts.boundary_negative_prompt import BOUNDARY_NEGATIVE
from app.prompts.edge_case_prompt import EDGE_CASE
from app.prompts.acceptance_criteria_prompt import ACCEPTANCE_CRITERIA

__all__ = [
    "REQUIREMENT_ANALYZER",
    "SCENARIO_GENERATOR",
    "TEST_CASE_GENERATOR",
    "BOUNDARY_NEGATIVE",
    "EDGE_CASE",
    "ACCEPTANCE_CRITERIA",
]
