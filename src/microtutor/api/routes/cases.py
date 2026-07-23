"""Case library API endpoints — serves parsed MGH ID Images cases."""

import json
import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

# Resolve paths relative to this file
# This file: src/microtutor/api/routes/cases.py
# Project root: 5 levels up
_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parent.parent.parent.parent.parent
_CASE_LIBRARY_JSON = _PROJECT_ROOT / "data" / "cases" / "case_library.json"
_ALL_CASES_DIR = _PROJECT_ROOT / "data" / "cases" / "ID_Images" / "All_cases"

# Load and cache on first request
_case_cache: list | None = None


def _load_cases() -> list:
    global _case_cache
    if _case_cache is None:
        if not _CASE_LIBRARY_JSON.exists():
            logger.error(f"case_library.json not found at {_CASE_LIBRARY_JSON}")
            _case_cache = []
        else:
            with open(_CASE_LIBRARY_JSON) as f:
                _case_cache = json.load(f)
            logger.info(f"Loaded {len(_case_cache)} cases from {_CASE_LIBRARY_JSON}")
    return _case_cache


def get_library_case(case_id: str) -> Optional[dict]:
    """Return a single case-library entry by id, or None."""
    if not case_id or not str(case_id).strip():
        return None
    needle = str(case_id).strip()
    for case in _load_cases():
        if case.get("id") == needle:
            return case
    return None


def organism_from_library_case(case: dict) -> Optional[str]:
    """Primary organism tag from a library case, if present."""
    for tag in case.get("tags") or []:
        if isinstance(tag, str) and tag.lower().startswith("organism:"):
            value = tag.split(":", 1)[1].strip()
            if value:
                return value.lower()
    return None


def lookup_cases_by_organism(organism: str) -> list[dict]:
    """Return case-library entries matching an organism name.

    Used by start_case to attach figure metadata for the DocentID image panel.
    Matches ``organism:…`` tags first, then falls back to title/diagnosis text.
    """
    if not organism or not str(organism).strip():
        return []

    needle = str(organism).strip().lower()
    # Normalize common variants (e.g. "staphylococcus aureus" vs "S. aureus")
    needle_compact = needle.replace(".", " ").replace("-", " ")
    needle_compact = " ".join(needle_compact.split())

    cases = _load_cases()
    tag_hits: list[dict] = []
    text_hits: list[dict] = []

    for case in cases:
        tags = case.get("tags") or []
        organism_tags = [
            t.split(":", 1)[1].strip().lower()
            for t in tags
            if isinstance(t, str) and t.lower().startswith("organism:")
        ]
        if any(
            needle in tag or needle_compact in tag or tag in needle or tag in needle_compact
            for tag in organism_tags
        ):
            tag_hits.append(case)
            continue

        blob = f"{case.get('title', '')} {case.get('diagnosis', '')}".lower()
        if needle in blob or needle_compact in blob:
            text_hits.append(case)

    return tag_hits or text_hits


@router.get("/cases")
async def list_cases(
    search: Optional[str] = Query(None, description="Full-text search across title, history, diagnosis"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Return a paginated list of all cases with summary fields only."""
    cases = _load_cases()

    if search:
        q = search.lower()
        cases = [
            c for c in cases
            if q in c.get("title", "").lower()
            or q in c.get("history", "").lower()
            or q in c.get("diagnosis", "").lower()
        ]

    total = len(cases)
    page = cases[offset: offset + limit]

    # Return summary only (no full text) for the list view
    summaries = [
        {
            "id": c["id"],
            "title": c["title"],
            "figures": c.get("figures", []),
            "tags": c.get("tags", []),
        }
        for c in page
    ]

    return {"total": total, "offset": offset, "limit": limit, "cases": summaries}


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """Return full case data for a single case."""
    cases = _load_cases()
    for c in cases:
        if c["id"] == case_id:
            return c
    raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")
