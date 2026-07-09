#!/usr/bin/env python3
"""Create and manage local docent.ID study users for testing.

This helper talks directly to the SQLite-backed study store so teammates can
seed student/reviewer/admin accounts even if the browser registration flow is
not yet working locally.
"""

from __future__ import annotations

import argparse
import importlib.util
import sqlite3
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
STORE_PATH = REPO_ROOT / "src" / "microtutor" / "core" / "study_store.py"


def load_study_store():
    spec = importlib.util.spec_from_file_location("docent_study_store", STORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load study store from {STORE_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_degrees(text: str) -> list[str]:
    return [value.strip() for value in text.split(",") if value.strip()]


def find_user(store, username: str):
    username_key = username.strip().casefold()
    for user in store.list_users():
        if user["username"].casefold() == username_key:
            return user
    return None


def cmd_list(args) -> int:
    store = load_study_store()
    users = store.list_users()
    if not users:
        print("No users found.")
        return 0

    for user in users:
        print(
            f"{user['username']}\trole={user['role']}\tactive={user['active']}"
            f"\tanon={user['anonymous_user_id']}\tname={user['display_name']}"
        )
    return 0


def cmd_create(args) -> int:
    store = load_study_store()
    try:
        user = store.create_user(
            username=args.username.strip(),
            password=args.password,
            display_name=args.name.strip(),
            training_level=args.training_level.strip(),
            year_in_program=args.year.strip(),
            degrees=parse_degrees(args.degrees),
            role=args.role,
        )
    except sqlite3.IntegrityError:
        print(f"Username '{args.username}' already exists.", file=sys.stderr)
        return 1

    print("Created user:")
    print(f"  username: {user['username']}")
    print(f"  role: {user['role']}")
    print(f"  anonymous_user_id: {user['anonymous_user_id']}")
    print(f"  study db: {store.DB_PATH}")
    return 0


def cmd_update_role(args) -> int:
    store = load_study_store()
    user = find_user(store, args.username)
    if user is None:
        print(f"User '{args.username}' not found.", file=sys.stderr)
        return 1

    updated = store.update_user(user["user_id"], role=args.role)
    print(f"Updated {updated['username']} to role={updated['role']}")
    return 0


def cmd_set_active(args) -> int:
    store = load_study_store()
    user = find_user(store, args.username)
    if user is None:
        print(f"User '{args.username}' not found.", file=sys.stderr)
        return 1

    updated = store.update_user(user["user_id"], active=args.active)
    print(f"Updated {updated['username']} to active={updated['active']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage local docent.ID study users stored in SQLite.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List current users")
    list_parser.set_defaults(func=cmd_list)

    create_parser = subparsers.add_parser("create", help="Create a new local user")
    create_parser.add_argument("--username", required=True)
    create_parser.add_argument("--password", required=True)
    create_parser.add_argument("--name", required=True, help="Display name")
    create_parser.add_argument(
        "--role",
        default="student",
        choices=["student", "reviewer", "admin"],
        help="Role to assign at creation time",
    )
    create_parser.add_argument("--training-level", default="")
    create_parser.add_argument("--year", default="", help="Year in program")
    create_parser.add_argument(
        "--degrees",
        default="",
        help="Comma-separated degrees, for example 'MD, PhD'",
    )
    create_parser.set_defaults(func=cmd_create)

    role_parser = subparsers.add_parser("set-role", help="Change a user's role")
    role_parser.add_argument("--username", required=True)
    role_parser.add_argument(
        "--role",
        required=True,
        choices=["student", "reviewer", "admin"],
    )
    role_parser.set_defaults(func=cmd_update_role)

    active_parser = subparsers.add_parser("set-active", help="Activate or deactivate a user")
    active_parser.add_argument("--username", required=True)
    active_group = active_parser.add_mutually_exclusive_group(required=True)
    active_group.add_argument("--active", action="store_true")
    active_group.add_argument("--inactive", dest="active", action="store_false")
    active_parser.set_defaults(func=cmd_set_active)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
