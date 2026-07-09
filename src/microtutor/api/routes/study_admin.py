"""Admin and task endpoints for the study workflow."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from microtutor.api.study_dependencies import get_current_user, require_admin
from microtutor.core.study_store import (
    create_task,
    get_task,
    get_task_summary,
    get_usage_summary,
    list_tasks,
    list_usage_events,
    list_users,
    record_usage_event,
    update_task_status,
    update_user,
)

router = APIRouter()


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


class UpdateUserRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    training_level: str | None = Field(default=None, max_length=120)
    year_in_program: str | None = Field(default=None, max_length=120)
    degrees: list[str] | None = None
    role: str | None = Field(default=None)
    active: bool | None = None

    @field_validator("display_name", "training_level", "year_in_program")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _normalize_text(value) if value is not None else value


class CreateTaskRequest(BaseModel):
    assignee_user_id: str = Field(..., min_length=1, max_length=120)
    task_type: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    case_id: str | None = Field(default=None, max_length=120)
    scheduled_for: str | None = Field(default=None, max_length=120)
    due_at: str | None = Field(default=None, max_length=120)

    @field_validator("task_type", "title", "description")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return _normalize_text(value)


class UpdateTaskStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(assigned|in_progress|completed)$")


@router.get("/admin/users")
async def get_users(admin: dict = Depends(require_admin)):
    users = list_users()
    record_usage_event(event_type="admin_view_users", user=admin, screen="admin_users")
    return {"users": users}


@router.patch("/admin/users/{user_id}")
async def patch_user(user_id: str, request: UpdateUserRequest, admin: dict = Depends(require_admin)):
    updated = update_user(
        user_id,
        display_name=request.display_name,
        training_level=request.training_level,
        year_in_program=request.year_in_program,
        degrees=request.degrees,
        role=request.role,
        active=request.active,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    record_usage_event(
        event_type="admin_update_user",
        user=admin,
        screen="admin_users",
        metadata={"target_user_id": user_id, "role": updated.get("role"), "active": updated.get("active")},
    )
    return {"user": updated}


@router.get("/admin/usage/summary")
async def usage_summary(admin: dict = Depends(require_admin)):
    record_usage_event(event_type="admin_view_usage_summary", user=admin, screen="admin_usage")
    return {"summary": get_usage_summary()}


@router.get("/admin/usage/events")
async def usage_events(admin: dict = Depends(require_admin)):
    record_usage_event(event_type="admin_view_usage_events", user=admin, screen="admin_usage")
    return {"events": list_usage_events()}


@router.get("/admin/tasks")
async def get_all_tasks(admin: dict = Depends(require_admin)):
    record_usage_event(event_type="admin_view_tasks", user=admin, screen="admin_tasks")
    return {"tasks": list_tasks()}


@router.post("/admin/tasks")
async def post_task(request: CreateTaskRequest, admin: dict = Depends(require_admin)):
    task = create_task(
        assignee_user_id=request.assignee_user_id,
        created_by_user_id=admin["user_id"],
        task_type=request.task_type,
        title=request.title,
        description=request.description,
        case_id=request.case_id,
        scheduled_for=request.scheduled_for,
        due_at=request.due_at,
    )
    record_usage_event(
        event_type="admin_create_task",
        user=admin,
        screen="admin_tasks",
        case_id=request.case_id,
        metadata={"task_type": request.task_type, "assignee_user_id": request.assignee_user_id},
    )
    return {"task": task}


@router.patch("/tasks/{task_id}")
async def patch_task_status(
    task_id: str,
    request: UpdateTaskStatusRequest,
    user: dict = Depends(get_current_user),
):
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if user["role"] != "admin" and task["assignee_user_id"] != user["user_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed to edit this task")

    updated = update_task_status(task_id, request.status)
    record_usage_event(
        event_type="update_task_status",
        user=user,
        screen="tasks",
        case_id=updated.get("case_id") if updated else None,
        metadata={"task_id": task_id, "status": request.status},
    )
    return {
        "task": updated,
        "summary": get_task_summary(user["user_id"]),
    }
