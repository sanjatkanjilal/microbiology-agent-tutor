"""Authentication and self-service user endpoints for the study app."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from microtutor.api.study_dependencies import get_current_user
from microtutor.core.study_store import (
    authenticate_user,
    clear_session,
    create_user,
    get_task_summary,
    list_reviewer_users,
    record_usage_event,
)

router = APIRouter()


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _require_non_empty(value: str, field_label: str) -> str:
    cleaned = _normalize_text(value)
    if not cleaned:
        raise ValueError(f"{field_label} is required")
    return cleaned


def _normalize_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        cleaned = _normalize_text(raw)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return _require_non_empty(value, "Username")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=8, max_length=256)
    display_name: str = Field(..., min_length=1, max_length=120)
    training_level: str = Field(default="", max_length=120)
    year_in_program: str = Field(default="", max_length=120)
    degrees: list[str] = Field(default_factory=list)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return _require_non_empty(value, "Username")

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        return _require_non_empty(value, "Full name")

    @field_validator("training_level", "year_in_program")
    @classmethod
    def normalize_optional_string(cls, value: str) -> str:
        return _normalize_text(value)

    @field_validator("degrees")
    @classmethod
    def normalize_degrees(cls, values: list[str]) -> list[str]:
        return _normalize_list(values)


class UsageEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=120)
    screen: str | None = Field(default=None, max_length=120)
    case_id: str | None = Field(default=None, max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def normalize_event_type(cls, value: str) -> str:
        return _normalize_text(value)


@router.post("/auth/login")
async def login(request: LoginRequest):
    user = authenticate_user(request.username, request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    record_usage_event(event_type="login", user=user, screen="login")
    user["task_summary"] = get_task_summary(user["user_id"])
    return {"user": user, "token": user["token"]}


@router.post("/auth/register")
async def register(request: RegisterRequest):
    try:
        user = create_user(
            username=request.username,
            password=request.password,
            display_name=request.display_name,
            training_level=request.training_level,
            year_in_program=request.year_in_program,
            degrees=request.degrees,
            role="student",
        )
    except sqlite3.IntegrityError as exc:
        message = str(exc)
        if "users.username" in message:
            detail = "Username already exists. Please choose a different username."
        else:
            detail = "Unable to create account because that record conflicts with an existing user."
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to create account: {exc}",
        ) from exc

    record_usage_event(
        event_type="register",
        user=user,
        screen="registration",
        metadata={
            "training_level": user.get("training_level"),
            "year_in_program": user.get("year_in_program"),
        },
    )
    return {"user": user}


@router.get("/auth/session")
async def get_session(user: dict = Depends(get_current_user)):
    user["task_summary"] = get_task_summary(user["user_id"])
    return {"user": user}


@router.post("/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    clear_session(user.get("token"))
    record_usage_event(event_type="logout", user=user, screen="logout")
    return {"message": "Logged out"}


@router.get("/users/reviewers")
async def get_reviewer_directory(user: dict = Depends(get_current_user)):
    reviewers = list_reviewer_users()
    record_usage_event(event_type="load_reviewer_directory", user=user, screen="tag_review")
    return {"reviewers": reviewers}


@router.get("/me/tasks")
async def get_my_tasks(user: dict = Depends(get_current_user)):
    from microtutor.core.study_store import list_tasks

    return {
        "tasks": list_tasks(assignee_user_id=user["user_id"]),
        "summary": get_task_summary(user["user_id"]),
    }


@router.post("/usage-events")
async def log_usage_event(request: UsageEventRequest, user: dict = Depends(get_current_user)):
    event = record_usage_event(
        event_type=request.event_type,
        user=user,
        screen=request.screen,
        case_id=request.case_id,
        metadata=request.metadata,
    )
    return {"event": event}
