"""Human review workflow for case tags."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from microtutor.api.study_dependencies import get_current_user
from microtutor.core.study_store import (
    get_tag_review_counts_by_case,
    get_tag_review_draft,
    list_reviewer_users,
    list_tag_reviews_for_case,
    record_usage_event,
    upsert_tag_review,
    upsert_tag_review_draft,
)

from .cases import _load_cases

router = APIRouter()
_REQUIRED_REVIEWERS_PER_CASE = 1


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        cleaned = _normalize_text(str(raw))
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _compare_values(values: list[str]) -> list[str]:
    return sorted(value.casefold() for value in _normalize_values(values))


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


def _find_case(case_id: str) -> dict[str, Any]:
    for case in _load_cases():
        if case.get("id") == case_id:
            return case
    raise HTTPException(status_code=404, detail=f"Case {case_id!r} not found")


def _require_review_access(user: dict) -> dict:
    if user.get("role") not in {"reviewer", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reviewer or admin access required",
        )
    return user


def _resolve_reviewer(user: dict, reviewer_user_id: str | None = None) -> dict[str, Any]:
    reviewers = list_reviewer_users()
    reviewer_map = {reviewer["user_id"]: reviewer for reviewer in reviewers}
    target_id = reviewer_user_id or user["user_id"]

    if user["role"] != "admin" and target_id != user["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only save tag reviews under your own reviewer account",
        )

    reviewer = reviewer_map.get(target_id)
    if reviewer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reviewer account not found",
        )
    return reviewer


def _case_review_summary(case_id: str, counts_by_case: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = counts_by_case.get(case_id, {})
    reviewer_count = int(counts.get("reviewer_count", 0))
    return {
        "reviewer_count": reviewer_count,
        "review_count": reviewer_count,
        "last_reviewed_at": counts.get("last_reviewed_at"),
        "needs_review": reviewer_count < _REQUIRED_REVIEWERS_PER_CASE,
        "required_reviews_per_case": _REQUIRED_REVIEWERS_PER_CASE,
    }


class TagReviewDraftRequest(BaseModel):
    reviewer_user_id: str | None = Field(default=None, max_length=120)
    organisms: list[str] = Field(default_factory=list)
    syndromes: list[str] = Field(default_factory=list)
    hosts: list[str] = Field(default_factory=list)
    comments: str = Field(default="", max_length=4000)

    @field_validator("organisms", "syndromes", "hosts", mode="before")
    @classmethod
    def normalize_list_input(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Expected a list")
        return value

    @field_validator("organisms", "syndromes", "hosts")
    @classmethod
    def clean_values(cls, values: list[str]) -> list[str]:
        return _normalize_values(values)

    @field_validator("comments")
    @classmethod
    def clean_comments(cls, value: str) -> str:
        return value.strip()


@router.get("/tag-review/cases")
async def list_tag_review_cases(
    search: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    reviewer = _require_review_access(user)
    cases = _load_cases()
    counts_by_case = get_tag_review_counts_by_case()

    case_summaries = []
    for case in cases:
      machine_answers = _machine_answers(case)
      review_summary = _case_review_summary(case["id"], counts_by_case)
      case_summaries.append(
          {
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
      )

    if search:
        q = search.casefold()
        case_summaries = [
            summary
            for summary in case_summaries
            if q in summary["id"].casefold()
            or q in summary["title"].casefold()
            or q in " ".join(
                summary["machine_answers"]["organisms"]
                + summary["machine_answers"]["syndromes"]
                + summary["machine_answers"]["hosts"]
            ).casefold()
        ]

    summary = {
        "total_cases": len(case_summaries),
        "reviewed_cases": sum(not case["needs_review"] for case in case_summaries),
        "pending_cases": sum(case["needs_review"] for case in case_summaries),
        "total_reviews": sum(case["review_count"] for case in case_summaries),
        "required_reviews_per_case": _REQUIRED_REVIEWERS_PER_CASE,
    }
    record_usage_event(event_type="view_tag_review_queue", user=reviewer, screen="tag_review")
    return {"summary": summary, "cases": case_summaries}


@router.get("/tag-review/cases/{case_id}")
async def get_tag_review_case(
    case_id: str,
    reviewer_user_id: str | None = Query(default=None),
    user: dict = Depends(get_current_user),
):
    reviewer = _require_review_access(user)
    target_reviewer = _resolve_reviewer(reviewer, reviewer_user_id)
    case = _find_case(case_id)
    counts_by_case = get_tag_review_counts_by_case()
    reviews = list_tag_reviews_for_case(case_id)
    draft = get_tag_review_draft(case_id, target_reviewer["user_id"])

    record_usage_event(
        event_type="open_tag_review_case",
        user=reviewer,
        screen="tag_review",
        case_id=case_id,
        metadata={"reviewer_user_id": target_reviewer["user_id"]},
    )
    return {
        "case": case,
        "machine_answers": _machine_answers(case),
        "review_summary": _case_review_summary(case_id, counts_by_case),
        "reviews": reviews,
        "current_draft": draft,
        "reviewer_directory": list_reviewer_users(),
        "selected_reviewer": target_reviewer,
    }


@router.put("/tag-review/cases/{case_id}/draft")
async def save_tag_review_draft(
    case_id: str,
    request: TagReviewDraftRequest,
    user: dict = Depends(get_current_user),
):
    reviewer = _require_review_access(user)
    target_reviewer = _resolve_reviewer(reviewer, request.reviewer_user_id)
    _find_case(case_id)

    draft = upsert_tag_review_draft(
        case_id=case_id,
        reviewer_user_id=target_reviewer["user_id"],
        reviewer_name=target_reviewer["display_name"],
        organisms=request.organisms,
        syndromes=request.syndromes,
        hosts=request.hosts,
        comments=request.comments,
    )
    record_usage_event(
        event_type="autosave_tag_review_draft",
        user=reviewer,
        screen="tag_review",
        case_id=case_id,
        metadata={"watermark_uuid": draft.get("watermark_uuid"), "reviewer_user_id": target_reviewer["user_id"]},
    )
    return {"draft": draft}


@router.post("/tag-review/cases/{case_id}/reviews")
async def submit_tag_review(
    case_id: str,
    request: TagReviewDraftRequest,
    user: dict = Depends(get_current_user),
):
    reviewer = _require_review_access(user)
    target_reviewer = _resolve_reviewer(reviewer, request.reviewer_user_id)
    case = _find_case(case_id)
    machine_answers = _machine_answers(case)

    decision = "accepted"
    if (
        _compare_values(request.organisms) != _compare_values(machine_answers["organisms"])
        or _compare_values(request.syndromes) != _compare_values(machine_answers["syndromes"])
        or _compare_values(request.hosts) != _compare_values(machine_answers["hosts"])
    ):
        decision = "modified"

    review = upsert_tag_review(
        case_id=case_id,
        reviewer_user_id=target_reviewer["user_id"],
        reviewer_name=target_reviewer["display_name"],
        organisms=request.organisms,
        syndromes=request.syndromes,
        hosts=request.hosts,
        comments=request.comments,
        decision=decision,
    )
    counts_by_case = get_tag_review_counts_by_case()
    record_usage_event(
        event_type="submit_tag_review",
        user=reviewer,
        screen="tag_review",
        case_id=case_id,
        metadata={"review_id": review.get("review_id"), "watermark_uuid": review.get("watermark_uuid")},
    )
    return {
        "message": "Review saved",
        "review": review,
        "review_summary": _case_review_summary(case_id, counts_by_case),
    }
