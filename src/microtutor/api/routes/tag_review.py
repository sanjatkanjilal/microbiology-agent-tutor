"""Human review workflow for case tags.

This router exposes a lightweight review layer on top of the case
library's current auto-parsed tags so subject-matter experts can verify
or correct organism, syndrome, and host labels in a shared UI.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from .cases import _PROJECT_ROOT, _load_cases

logger = logging.getLogger(__name__)
router = APIRouter()

_REVIEW_STORE_PATH = _PROJECT_ROOT / "data" / "cases" / "tag_reviews.json"
_STORE_LOCK = Lock()
_REQUIRED_REVIEWERS_PER_CASE = 1


class TagReviewSubmission(BaseModel):
    """Validated payload for a single expert review."""

    reviewer_name: str = Field(..., min_length=1, max_length=80)
    organisms: list[str] = Field(default_factory=list)
    syndromes: list[str] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4000)

    @field_validator("reviewer_name")
    @classmethod
    def clean_reviewer_name(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("reviewer_name cannot be empty")
        return cleaned

    @field_validator("organisms", "syndromes", "hosts", mode="before")
    @classmethod
    def default_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Expected a list of strings")
        return value

    @field_validator("organisms", "syndromes", "hosts")
    @classmethod
    def clean_values(cls, values: list[str]) -> list[str]:
        return _normalize_values(values)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str) -> str:
        return value.strip()


def _normalize_values(values: list[str]) -> list[str]:
    """Trim, deduplicate, and preserve order for user-entered tag lists."""
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        if raw is None:
            continue
        cleaned = " ".join(str(raw).split()).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _compare_values(values: list[str]) -> list[str]:
    """Canonical representation for equality checks that ignores order/case."""
    return sorted(v.casefold() for v in _normalize_values(values))


def _tags_by_type(tags: list[str] | None, tag_type: str) -> list[str]:
    prefix = f"{tag_type}:"
    return [
        tag[len(prefix):].strip()
        for tag in (tags or [])
        if isinstance(tag, str) and tag.startswith(prefix)
    ]


def _machine_answers(case: dict[str, Any]) -> dict[str, list[str]]:
    tags = case.get("tags", [])
    return {
        "organisms": _normalize_values(_tags_by_type(tags, "organism")),
        "syndromes": _normalize_values(_tags_by_type(tags, "syndrome")),
        "hosts": _normalize_values(_tags_by_type(tags, "host")),
    }


def _empty_store() -> dict[str, Any]:
    return {
        "version": 1,
        "required_reviews_per_case": _REQUIRED_REVIEWERS_PER_CASE,
        "cases": {},
    }


def _load_review_store() -> dict[str, Any]:
    if not _REVIEW_STORE_PATH.exists():
        return _empty_store()

    with open(_REVIEW_STORE_PATH) as handle:
        store = json.load(handle)

    if not isinstance(store, dict):
        raise ValueError(f"Invalid tag review store at {_REVIEW_STORE_PATH}")

    store.setdefault("version", 1)
    store.setdefault("required_reviews_per_case", _REQUIRED_REVIEWERS_PER_CASE)
    store.setdefault("cases", {})

    if not isinstance(store["cases"], dict):
        raise ValueError(f"Invalid tag review cases payload at {_REVIEW_STORE_PATH}")

    return store


def _save_review_store(store: dict[str, Any]) -> None:
    _REVIEW_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(f"{_REVIEW_STORE_PATH}.tmp")
    with open(tmp_path, "w") as handle:
        json.dump(store, handle, indent=2)
        handle.write("\n")
    tmp_path.replace(_REVIEW_STORE_PATH)


def _public_review(review: dict[str, Any]) -> dict[str, Any]:
    return {
        "reviewer_name": review["reviewer_name"],
        "organisms": review.get("organisms", []),
        "syndromes": review.get("syndromes", []),
        "hosts": review.get("hosts", []),
        "notes": review.get("notes", ""),
        "decision": review.get("decision", "modified"),
        "submitted_at": review.get("submitted_at"),
    }


def _case_reviews(case_id: str, store: dict[str, Any]) -> list[dict[str, Any]]:
    case_entry = store.get("cases", {}).get(case_id, {})
    reviews = case_entry.get("reviews", [])
    if not isinstance(reviews, list):
        return []
    return [
        review
        for review in reviews
        if isinstance(review, dict) and review.get("reviewer_name")
    ]


def _case_review_summary(case_id: str, store: dict[str, Any]) -> dict[str, Any]:
    reviews = _case_reviews(case_id, store)
    reviewers = [review["reviewer_name"] for review in reviews]
    reviewer_count = len(reviewers)
    last_reviewed_at = max((review.get("submitted_at") for review in reviews if review.get("submitted_at")), default=None)
    required_reviews = int(store.get("required_reviews_per_case", _REQUIRED_REVIEWERS_PER_CASE))

    return {
        "reviewer_count": reviewer_count,
        "reviewers": reviewers,
        "review_count": reviewer_count,
        "last_reviewed_at": last_reviewed_at,
        "needs_review": reviewer_count < required_reviews,
        "required_reviews_per_case": required_reviews,
    }


def _case_summary(case: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    review_summary = _case_review_summary(case["id"], store)
    machine_answers = _machine_answers(case)
    return {
        "id": case["id"],
        "title": case.get("title", ""),
        "machine_answers": machine_answers,
        "machine_answer_counts": {
            "organisms": len(machine_answers["organisms"]),
            "syndromes": len(machine_answers["syndromes"]),
            "hosts": len(machine_answers["hosts"]),
        },
        "figures_count": len(case.get("figures", [])),
        **review_summary,
    }


def _list_summary(case_summaries: list[dict[str, Any]], store: dict[str, Any]) -> dict[str, Any]:
    reviewed_cases = sum(not case["needs_review"] for case in case_summaries)
    total_reviews = sum(case["review_count"] for case in case_summaries)
    return {
        "total_cases": len(case_summaries),
        "reviewed_cases": reviewed_cases,
        "pending_cases": len(case_summaries) - reviewed_cases,
        "total_reviews": total_reviews,
        "required_reviews_per_case": int(store.get("required_reviews_per_case", _REQUIRED_REVIEWERS_PER_CASE)),
    }


def _find_case(case_id: str) -> dict[str, Any]:
    for case in _load_cases():
        if case.get("id") == case_id:
            return case
    raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")


@router.get("/tag-review/cases")
async def list_tag_review_cases(
    search: Optional[str] = Query(None, description="Filter by case ID, title, history, or diagnosis"),
    status: str = Query("all", pattern="^(all|needs_review|reviewed)$"),
):
    """Return review-oriented case summaries and queue-level counters."""
    cases = _load_cases()
    with _STORE_LOCK:
        store = _load_review_store()

    case_summaries = [_case_summary(case, store) for case in cases]

    if search:
        query = search.casefold()
        matched_ids = {
            case["id"]
            for case in cases
            if query in case.get("id", "").casefold()
            or query in case.get("title", "").casefold()
            or query in case.get("history", "").casefold()
            or query in case.get("diagnosis", "").casefold()
        }
        case_summaries = [summary for summary in case_summaries if summary["id"] in matched_ids]

    if status == "needs_review":
        case_summaries = [summary for summary in case_summaries if summary["needs_review"]]
    elif status == "reviewed":
        case_summaries = [summary for summary in case_summaries if not summary["needs_review"]]

    return {
        "summary": _list_summary(case_summaries, store),
        "cases": case_summaries,
    }


@router.get("/tag-review/cases/{case_id}")
async def get_tag_review_case(case_id: str):
    """Return a full case plus machine suggestions and prior expert reviews."""
    case = _find_case(case_id)

    with _STORE_LOCK:
        store = _load_review_store()

    reviews = sorted(
        (_public_review(review) for review in _case_reviews(case_id, store)),
        key=lambda review: review.get("submitted_at") or "",
        reverse=True,
    )

    return {
        "case": case,
        "machine_answers": _machine_answers(case),
        "review_summary": _case_review_summary(case_id, store),
        "reviews": reviews,
    }


@router.post("/tag-review/cases/{case_id}/reviews")
async def submit_tag_review(case_id: str, submission: TagReviewSubmission):
    """Create or update a review for a case by reviewer name."""
    case = _find_case(case_id)
    machine_answers = _machine_answers(case)

    decision: Literal["accepted", "modified"] = "accepted"
    if (
        _compare_values(submission.organisms) != _compare_values(machine_answers["organisms"])
        or _compare_values(submission.syndromes) != _compare_values(machine_answers["syndromes"])
        or _compare_values(submission.hosts) != _compare_values(machine_answers["hosts"])
    ):
        decision = "modified"

    stored_review = {
        "reviewer_name": submission.reviewer_name,
        "reviewer_key": submission.reviewer_name.casefold(),
        "organisms": submission.organisms,
        "syndromes": submission.syndromes,
        "hosts": submission.hosts,
        "notes": submission.notes,
        "decision": decision,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }

    with _STORE_LOCK:
        store = _load_review_store()
        case_entry = store.setdefault("cases", {}).setdefault(case_id, {"reviews": []})
        reviews = case_entry.setdefault("reviews", [])

        replaced = False
        for index, existing in enumerate(reviews):
            if existing.get("reviewer_key") == stored_review["reviewer_key"]:
                reviews[index] = stored_review
                replaced = True
                break

        if not replaced:
            reviews.append(stored_review)

        _save_review_store(store)
        review_summary = _case_review_summary(case_id, store)

    logger.info(
        "Saved tag review for %s by %s (%s)",
        case_id,
        submission.reviewer_name,
        decision,
    )

    return {
        "message": "Review saved",
        "review": _public_review(stored_review),
        "review_summary": review_summary,
        "case_summary": _case_summary(case, store),
    }
