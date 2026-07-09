"""SQLite-backed study/admin store for docent.ID.

This module provides a lightweight local database for:
- user accounts and roles
- login sessions
- reviewer tasks
- usage analytics events
- tag review drafts and finalized reviews

It is intentionally separate from the optional Postgres logging setup so
the study/admin workflow works locally out of the box.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = REPO_ROOT / "data" / "study_admin.db"
DEFAULT_SESSION_DAYS = 30
PASSWORD_ITERATIONS = 260_000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=True)


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        _initialize(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            anonymous_user_id TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'reviewer', 'admin')),
            training_level TEXT,
            year_in_program TEXT,
            degrees_json TEXT,
            created_at TEXT NOT NULL,
            last_login_at TEXT,
            intake_submitted_at TEXT,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS auth_sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            assignee_user_id TEXT NOT NULL,
            created_by_user_id TEXT,
            task_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            case_id TEXT,
            scheduled_for TEXT,
            due_at TEXT,
            status TEXT NOT NULL CHECK(status IN ('assigned', 'in_progress', 'completed')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(assignee_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(created_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS usage_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT,
            username TEXT,
            role TEXT,
            event_type TEXT NOT NULL,
            screen TEXT,
            case_id TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tag_review_drafts (
            draft_id TEXT PRIMARY KEY,
            watermark_uuid TEXT NOT NULL,
            case_id TEXT NOT NULL,
            reviewer_user_id TEXT NOT NULL,
            reviewer_name TEXT NOT NULL,
            organisms_json TEXT NOT NULL,
            syndromes_json TEXT NOT NULL,
            hosts_json TEXT NOT NULL,
            comments TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(case_id, reviewer_user_id),
            FOREIGN KEY(reviewer_user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tag_reviews (
            review_id TEXT PRIMARY KEY,
            watermark_uuid TEXT NOT NULL,
            case_id TEXT NOT NULL,
            reviewer_user_id TEXT NOT NULL,
            reviewer_name TEXT NOT NULL,
            organisms_json TEXT NOT NULL,
            syndromes_json TEXT NOT NULL,
            hosts_json TEXT NOT NULL,
            comments TEXT,
            decision TEXT NOT NULL CHECK(decision IN ('accepted', 'modified')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(reviewer_user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
    )
    _ensure_default_admin(conn)


def _ensure_default_admin(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT user_id FROM users WHERE username = ?", ("admin",)).fetchone()
    if existing:
        return

    now = utc_now_iso()
    admin_user_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (
            user_id, username, anonymous_user_id, display_name, password_hash, role,
            training_level, year_in_program, degrees_json, created_at, intake_submitted_at, active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            admin_user_id,
            "admin",
            "anon-admin",
            "Administrator",
            hash_password("admin"),
            "admin",
            "Administrator",
            "",
            _json_dump([]),
            now,
            now,
        ),
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iteration_text, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(digest_b64.encode("ascii"))
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def serialize_user(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "anonymous_user_id": row["anonymous_user_id"],
        "display_name": row["display_name"],
        "role": row["role"],
        "training_level": row["training_level"] or "",
        "year_in_program": row["year_in_program"] or "",
        "degrees": _json_load(row["degrees_json"], []),
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
        "intake_submitted_at": row["intake_submitted_at"],
        "active": bool(row["active"]),
    }


def create_user(
    *,
    username: str,
    password: str,
    display_name: str,
    training_level: str,
    year_in_program: str,
    degrees: list[str],
    role: str = "student",
) -> dict[str, Any]:
    user_id = str(uuid.uuid4())
    anonymous_user_id = f"anon-{secrets.token_hex(4)}"
    now = utc_now_iso()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                user_id, username, anonymous_user_id, display_name, password_hash, role,
                training_level, year_in_program, degrees_json, created_at, intake_submitted_at, active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                user_id,
                username,
                anonymous_user_id,
                display_name,
                hash_password(password),
                role,
                training_level,
                year_in_program,
                _json_dump(degrees),
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        return serialize_user(row) or {}


def list_users() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at ASC"
        ).fetchall()
    return [serialize_user(row) for row in rows if row is not None]


def update_user(
    user_id: str,
    *,
    display_name: str | None = None,
    training_level: str | None = None,
    year_in_program: str | None = None,
    degrees: list[str] | None = None,
    role: str | None = None,
    active: bool | None = None,
) -> dict[str, Any] | None:
    fields: list[str] = []
    values: list[Any] = []
    if display_name is not None:
        fields.append("display_name = ?")
        values.append(display_name)
    if training_level is not None:
        fields.append("training_level = ?")
        values.append(training_level)
    if year_in_program is not None:
        fields.append("year_in_program = ?")
        values.append(year_in_program)
    if degrees is not None:
        fields.append("degrees_json = ?")
        values.append(_json_dump(degrees))
    if role is not None:
        fields.append("role = ?")
        values.append(role)
    if active is not None:
        fields.append("active = ?")
        values.append(1 if active else 0)
    if not fields:
        return get_user_by_id(user_id)

    values.append(user_id)
    with get_connection() as conn:
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?", values)
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return serialize_user(row)


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return row


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return serialize_user(row)


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or not bool(row["active"]):
            return None
        if not verify_password(password, row["password_hash"]):
            return None

        now = utc_now_iso()
        conn.execute("UPDATE users SET last_login_at = ? WHERE user_id = ?", (now, row["user_id"]))
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=DEFAULT_SESSION_DAYS)).isoformat()
        conn.execute(
            """
            INSERT INTO auth_sessions (token, user_id, created_at, last_seen_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token, row["user_id"], now, now, expires_at),
        )
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (row["user_id"],)).fetchone()
    payload = serialize_user(user)
    if payload is None:
        return None
    payload["token"] = token
    return payload


def get_user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    now = utc_now_iso()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT u.*, s.token
            FROM auth_sessions s
            JOIN users u ON u.user_id = s.user_id
            WHERE s.token = ? AND s.expires_at >= ? AND u.active = 1
            """,
            (token, now),
        ).fetchone()
        if row is None:
            return None
        conn.execute("UPDATE auth_sessions SET last_seen_at = ? WHERE token = ?", (now, token))
    user = serialize_user(row)
    if user is None:
        return None
    user["token"] = token
    return user


def clear_session(token: str | None) -> None:
    if not token:
        return
    with get_connection() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))


def record_usage_event(
    *,
    event_type: str,
    user: dict[str, Any] | None = None,
    screen: str | None = None,
    case_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = str(uuid.uuid4())
    created_at = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO usage_events (
                event_id, user_id, username, role, event_type, screen, case_id, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                (user or {}).get("user_id"),
                (user or {}).get("username"),
                (user or {}).get("role"),
                event_type,
                screen,
                case_id,
                _json_dump(metadata or {}),
                created_at,
            ),
        )
    return {
        "event_id": event_id,
        "created_at": created_at,
    }


def get_usage_summary() -> dict[str, Any]:
    with get_connection() as conn:
        total_users = conn.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0]
        total_events = conn.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        total_reviews = conn.execute("SELECT COUNT(*) FROM tag_reviews").fetchone()[0]
        total_drafts = conn.execute("SELECT COUNT(*) FROM tag_review_drafts").fetchone()[0]
        last_event = conn.execute("SELECT MAX(created_at) FROM usage_events").fetchone()[0]
        events_by_type = [
            {
                "event_type": row["event_type"],
                "count": row["count"],
            }
            for row in conn.execute(
                """
                SELECT event_type, COUNT(*) AS count
                FROM usage_events
                GROUP BY event_type
                ORDER BY count DESC
                """
            ).fetchall()
        ]
        events_by_user = [
            {
                "username": row["username"] or "anonymous",
                "count": row["count"],
            }
            for row in conn.execute(
                """
                SELECT COALESCE(username, 'anonymous') AS username, COUNT(*) AS count
                FROM usage_events
                GROUP BY COALESCE(username, 'anonymous')
                ORDER BY count DESC
                LIMIT 20
                """
            ).fetchall()
        ]
    return {
        "total_users": total_users,
        "total_events": total_events,
        "total_reviews": total_reviews,
        "total_drafts": total_drafts,
        "last_event_at": last_event,
        "events_by_type": events_by_type,
        "events_by_user": events_by_user,
    }


def list_usage_events(limit: int = 200) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT event_id, user_id, username, role, event_type, screen, case_id, metadata_json, created_at
            FROM usage_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "event_id": row["event_id"],
            "user_id": row["user_id"],
            "username": row["username"],
            "role": row["role"],
            "event_type": row["event_type"],
            "screen": row["screen"],
            "case_id": row["case_id"],
            "metadata": _json_load(row["metadata_json"], {}),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def create_task(
    *,
    assignee_user_id: str,
    created_by_user_id: str | None,
    task_type: str,
    title: str,
    description: str,
    case_id: str | None,
    scheduled_for: str | None,
    due_at: str | None,
) -> dict[str, Any]:
    task_id = str(uuid.uuid4())
    now = utc_now_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (
                task_id, assignee_user_id, created_by_user_id, task_type, title, description,
                case_id, scheduled_for, due_at, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'assigned', ?, ?)
            """,
            (
                task_id,
                assignee_user_id,
                created_by_user_id,
                task_type,
                title,
                description,
                case_id,
                scheduled_for,
                due_at,
                now,
                now,
            ),
        )
    return get_task(task_id) or {}


def get_task(task_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                t.*,
                assignee.display_name AS assignee_name,
                assignee.username AS assignee_username,
                creator.display_name AS created_by_name
            FROM tasks t
            JOIN users assignee ON assignee.user_id = t.assignee_user_id
            LEFT JOIN users creator ON creator.user_id = t.created_by_user_id
            WHERE t.task_id = ?
            """,
            (task_id,),
        ).fetchone()
    return serialize_task(row)


def serialize_task(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "task_id": row["task_id"],
        "assignee_user_id": row["assignee_user_id"],
        "assignee_name": row["assignee_name"],
        "assignee_username": row["assignee_username"],
        "created_by_user_id": row["created_by_user_id"],
        "created_by_name": row["created_by_name"],
        "task_type": row["task_type"],
        "title": row["title"],
        "description": row["description"] or "",
        "case_id": row["case_id"],
        "scheduled_for": row["scheduled_for"],
        "due_at": row["due_at"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_tasks(*, assignee_user_id: str | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT
            t.*,
            assignee.display_name AS assignee_name,
            assignee.username AS assignee_username,
            creator.display_name AS created_by_name
        FROM tasks t
        JOIN users assignee ON assignee.user_id = t.assignee_user_id
        LEFT JOIN users creator ON creator.user_id = t.created_by_user_id
    """
    params: list[Any] = []
    if assignee_user_id:
        query += " WHERE t.assignee_user_id = ?"
        params.append(assignee_user_id)
    query += " ORDER BY CASE t.status WHEN 'assigned' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, t.created_at DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [task for row in rows if (task := serialize_task(row)) is not None]


def update_task_status(task_id: str, status: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
            (status, utc_now_iso(), task_id),
        )
    return get_task(task_id)


def get_task_summary(user_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        pending = conn.execute(
            """
            SELECT COUNT(*)
            FROM tasks
            WHERE assignee_user_id = ? AND status != 'completed'
            """,
            (user_id,),
        ).fetchone()[0]
        completed = conn.execute(
            """
            SELECT COUNT(*)
            FROM tasks
            WHERE assignee_user_id = ? AND status = 'completed'
            """,
            (user_id,),
        ).fetchone()[0]
    return {
        "pending_count": pending,
        "completed_count": completed,
    }


def list_reviewer_users() -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM users
            WHERE active = 1 AND role IN ('reviewer', 'admin')
            ORDER BY display_name COLLATE NOCASE
            """
        ).fetchall()
    return [serialize_user(row) for row in rows if row is not None]


def get_tag_review_draft(case_id: str, reviewer_user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM tag_review_drafts
            WHERE case_id = ? AND reviewer_user_id = ?
            """,
            (case_id, reviewer_user_id),
        ).fetchone()
    return serialize_tag_review_draft(row)


def serialize_tag_review_draft(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "draft_id": row["draft_id"],
        "watermark_uuid": row["watermark_uuid"],
        "case_id": row["case_id"],
        "reviewer_user_id": row["reviewer_user_id"],
        "reviewer_name": row["reviewer_name"],
        "organisms": _json_load(row["organisms_json"], []),
        "syndromes": _json_load(row["syndromes_json"], []),
        "hosts": _json_load(row["hosts_json"], []),
        "comments": row["comments"] or "",
        "updated_at": row["updated_at"],
    }


def upsert_tag_review_draft(
    *,
    case_id: str,
    reviewer_user_id: str,
    reviewer_name: str,
    organisms: list[str],
    syndromes: list[str],
    hosts: list[str],
    comments: str,
) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT draft_id, watermark_uuid
            FROM tag_review_drafts
            WHERE case_id = ? AND reviewer_user_id = ?
            """,
            (case_id, reviewer_user_id),
        ).fetchone()
        draft_id = row["draft_id"] if row else str(uuid.uuid4())
        watermark_uuid = row["watermark_uuid"] if row else str(uuid.uuid4())
        updated_at = utc_now_iso()
        conn.execute(
            """
            INSERT INTO tag_review_drafts (
                draft_id, watermark_uuid, case_id, reviewer_user_id, reviewer_name,
                organisms_json, syndromes_json, hosts_json, comments, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id, reviewer_user_id) DO UPDATE SET
                reviewer_name = excluded.reviewer_name,
                organisms_json = excluded.organisms_json,
                syndromes_json = excluded.syndromes_json,
                hosts_json = excluded.hosts_json,
                comments = excluded.comments,
                updated_at = excluded.updated_at
            """,
            (
                draft_id,
                watermark_uuid,
                case_id,
                reviewer_user_id,
                reviewer_name,
                _json_dump(organisms),
                _json_dump(syndromes),
                _json_dump(hosts),
                comments,
                updated_at,
            ),
        )
        saved = conn.execute(
            """
            SELECT *
            FROM tag_review_drafts
            WHERE case_id = ? AND reviewer_user_id = ?
            """,
            (case_id, reviewer_user_id),
        ).fetchone()
    return serialize_tag_review_draft(saved) or {}


def list_tag_reviews_for_case(case_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tag_reviews
            WHERE case_id = ?
            ORDER BY updated_at DESC
            """,
            (case_id,),
        ).fetchall()
    return [review for row in rows if (review := serialize_tag_review(row)) is not None]


def serialize_tag_review(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "review_id": row["review_id"],
        "watermark_uuid": row["watermark_uuid"],
        "case_id": row["case_id"],
        "reviewer_user_id": row["reviewer_user_id"],
        "reviewer_name": row["reviewer_name"],
        "organisms": _json_load(row["organisms_json"], []),
        "syndromes": _json_load(row["syndromes_json"], []),
        "hosts": _json_load(row["hosts_json"], []),
        "comments": row["comments"] or "",
        "decision": row["decision"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_tag_review(
    *,
    case_id: str,
    reviewer_user_id: str,
    reviewer_name: str,
    organisms: list[str],
    syndromes: list[str],
    hosts: list[str],
    comments: str,
    decision: str,
) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT review_id, watermark_uuid, created_at
            FROM tag_reviews
            WHERE case_id = ? AND reviewer_user_id = ?
            """,
            (case_id, reviewer_user_id),
        ).fetchone()
        review_id = row["review_id"] if row else str(uuid.uuid4())
        watermark_uuid = row["watermark_uuid"] if row else str(uuid.uuid4())
        created_at = row["created_at"] if row else utc_now_iso()
        updated_at = utc_now_iso()
        conn.execute(
            """
            INSERT INTO tag_reviews (
                review_id, watermark_uuid, case_id, reviewer_user_id, reviewer_name,
                organisms_json, syndromes_json, hosts_json, comments, decision, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(review_id) DO UPDATE SET
                reviewer_name = excluded.reviewer_name,
                organisms_json = excluded.organisms_json,
                syndromes_json = excluded.syndromes_json,
                hosts_json = excluded.hosts_json,
                comments = excluded.comments,
                decision = excluded.decision,
                updated_at = excluded.updated_at
            """,
            (
                review_id,
                watermark_uuid,
                case_id,
                reviewer_user_id,
                reviewer_name,
                _json_dump(organisms),
                _json_dump(syndromes),
                _json_dump(hosts),
                comments,
                decision,
                created_at,
                updated_at,
            ),
        )
        saved = conn.execute(
            "SELECT * FROM tag_reviews WHERE review_id = ?",
            (review_id,),
        ).fetchone()
    return serialize_tag_review(saved) or {}


def get_tag_review_counts_by_case() -> dict[str, dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                case_id,
                COUNT(*) AS reviewer_count,
                MAX(updated_at) AS last_reviewed_at
            FROM tag_reviews
            GROUP BY case_id
            """
        ).fetchall()
    return {
        row["case_id"]: {
            "reviewer_count": row["reviewer_count"],
            "last_reviewed_at": row["last_reviewed_at"],
        }
        for row in rows
    }
