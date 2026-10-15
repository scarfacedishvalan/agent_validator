from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.connection import connect


def create_profile(
    database_path: Path,
    name: str,
    field_keys: list[str],
    settings: dict[str, Any],
    combination_mode: str,
) -> dict[str, Any]:
    profile_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with connect(database_path) as connection:
        connection.execute(
            """INSERT INTO mutation_profiles
               (id, name, field_keys_json, settings_json, combination_mode, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                profile_id,
                name,
                json.dumps(field_keys),
                json.dumps(settings, allow_nan=False),
                combination_mode,
                now,
                now,
            ),
        )
    return get_profile(database_path, profile_id)  # type: ignore[return-value]


def update_profile(
    database_path: Path,
    profile_id: str,
    name: str,
    field_keys: list[str],
    settings: dict[str, Any],
    combination_mode: str,
) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).isoformat()
    with connect(database_path) as connection:
        cursor = connection.execute(
            """UPDATE mutation_profiles
               SET name = ?, field_keys_json = ?, settings_json = ?, combination_mode = ?, updated_at = ?
               WHERE id = ?""",
            (
                name,
                json.dumps(field_keys),
                json.dumps(settings, allow_nan=False),
                combination_mode,
                now,
                profile_id,
            ),
        )
        if cursor.rowcount == 0:
            return None
    return get_profile(database_path, profile_id)


def list_profiles(database_path: Path) -> tuple[list[dict[str, Any]], int]:
    with connect(database_path) as connection:
        total = connection.execute("SELECT COUNT(*) FROM mutation_profiles").fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM mutation_profiles ORDER BY updated_at DESC"
        ).fetchall()
    return [_profile_from_row(row) for row in rows], int(total)


def get_profile(database_path: Path, profile_id: str) -> dict[str, Any] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM mutation_profiles WHERE id = ?", (profile_id,)
        ).fetchone()
    return _profile_from_row(row) if row else None


def delete_profile(database_path: Path, profile_id: str) -> bool:
    with connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM mutation_profiles WHERE id = ?", (profile_id,)
        )
    return cursor.rowcount > 0


def _profile_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "field_keys": json.loads(row["field_keys_json"]),
        "settings": json.loads(row["settings_json"]),
        "combination_mode": row["combination_mode"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
