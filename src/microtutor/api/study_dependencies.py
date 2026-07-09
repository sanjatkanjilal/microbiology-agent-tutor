"""Shared auth helpers for the SQLite-backed study/admin workflow."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status

from microtutor.core.study_store import get_user_for_token


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix):].strip()
    return None


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    token = _extract_token(authorization)
    user = get_user_for_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user
