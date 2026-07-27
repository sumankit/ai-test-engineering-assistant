"""
Requirement Extraction Tool
----------------------------
Deliberately NOT an LLM call. Turns parsed document text into a list of
structured Requirement objects using pattern matching. Keeping this
deterministic means: (a) it's free and instant, (b) it's testable with
plain unit tests, (c) the LLM agents downstream get a clean, consistent
input shape regardless of how a given document happens to be worded.

Two extraction strategies, tried in order:
1. "FR-N: Title" style (what both sample requirement docs in this
   project use) -- captures Description / Validation Conditions /
   Role-Based Conditions / Example Input / Example Output / Edge Case
   as sub-fields when present, and folds them into `description` so
   later agents see the full context.
2. Generic fallback: numbered/bulleted top-level sentences become
   REQ-001, REQ-002, ... when no FR-N pattern is found.
"""
from __future__ import annotations
import re
from app.schemas.schemas import Requirement

_FR_HEADER = re.compile(r"^\s*(?:[*\-•●]\s*)?(?:\*\*)?(FR-\d+)(?:\*\*)?\s*:\s*(.+)$")
_SUBFIELD = re.compile(
    r"^\s*(?:[○\-*•●]\s*)?(?:\*\*)?"
    r"(Description|Validation Conditions|Role-Based Conditions|"
    r"Example Input|Example Output|Edge Case)"
    r"(?:\*\*)?\s*:?\s*(.*)$",
    re.IGNORECASE,
)


def _extract_fr_style(text: str) -> list[Requirement]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    reqs: list[Requirement] = []
    current_fr_id = None
    current_fr_title = None
    current_subfields = {}
    current_field = None

    def flush():
        if not current_fr_id:
            return
            
        section_name = f"{current_fr_id} {current_fr_title}"
        
        desc_text = current_subfields.get("Description", "").strip() or current_fr_title
        
        validations = []
        if "Validation Conditions" in current_subfields:
            val_text = current_subfields["Validation Conditions"].strip()
            validations = [r.strip() + ("." if not r.strip().endswith(".") else "") for r in val_text.split(". ") if r.strip()]

        reqs.append(Requirement(
            req_id=f"{current_fr_id}",
            title=f"{current_fr_title}",
            description=desc_text,
            section=section_name,
            raw_text=f"Description: {desc_text}",
            type="Functional",
            validations=validations
        ))

        if "Role-Based Conditions" in current_subfields:
            role_text = current_subfields["Role-Based Conditions"].strip()
            role_val = None
            if "unauthenticated" in role_text.lower():
                role_val = "Unauthenticated User"
            elif "authenticated users with the provider role" in role_text.lower():
                role_val = "Provider"
            elif "authenticated users with the patient role" in role_text.lower():
                role_val = "Patient"
            elif "patient" in role_text.lower():
                role_val = "Patient"
            elif "provider" in role_text.lower():
                role_val = "Provider"
            
            reqs.append(Requirement(
                req_id=f"{current_fr_id}-Constraint",
                title=f"{current_fr_title} (Role Constraint)",
                description=role_text,
                section=section_name,
                raw_text=f"Role-Based Condition: {role_text}",
                type="Technical Constraint",
                role=role_val
            ))

        if "Edge Case" in current_subfields:
            edge_text = current_subfields["Edge Case"].strip()
            reqs.append(Requirement(
                req_id=f"{current_fr_id}-Edge",
                title=f"{current_fr_title} (Edge Case)",
                description=edge_text,
                section=section_name,
                raw_text=f"Edge Case: {edge_text}",
                type="Edge Case"
            ))

    for line in lines:
        m = _FR_HEADER.match(line)
        if m:
            flush()
            current_fr_id = m.group(1).strip()
            current_fr_title = m.group(2).strip(" *")
            current_subfields = {}
            current_field = None
            continue
        if not current_fr_id:
            continue
        sm = _SUBFIELD.match(line)
        if sm:
            field_raw = sm.group(1)
            key = {
                "description": "Description",
                "validation conditions": "Validation Conditions",
                "role-based conditions": "Role-Based Conditions",
                "example input": "Example Input",
                "example output": "Example Output",
                "edge case": "Edge Case",
            }[field_raw.lower()]
            current_field = key
            current_subfields[current_field] = sm.group(2)
            continue
        if current_field and line.strip():
            current_subfields[current_field] = current_subfields.get(current_field, "") + " " + line.strip()

    flush()
    return reqs


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _extract_generic(text: str) -> list[Requirement]:
    """Fallback for documents with no FR-N headers: one requirement per
    "shall/must/should" sentence, per the assignment's own worked example."""
    reqs: list[Requirement] = []
    candidates = [
        ln.strip("-*• \t")
        for ln in text.splitlines()
        if re.search(r"\b(shall|must|should)\b", ln, re.IGNORECASE) and len(ln.strip()) > 15
    ]
    for i, sentence in enumerate(candidates, start=1):
        reqs.append(Requirement(
            req_id=f"REQ-{i:03d}",
            title=sentence[:60].strip(),
            description=sentence,
            raw_text=sentence,
        ))
    return reqs


def extract_requirements(text: str) -> list[Requirement]:
    text = text.replace('\u200b', '')
    reqs = _extract_fr_style(text)
    if reqs:
        return reqs
    return _extract_generic(text)
