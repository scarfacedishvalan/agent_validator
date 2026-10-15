from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.connection import connect


def create_snapshot(database_path: Path, name: str, as_of: str, values: dict[str, float]) -> dict[str, Any]:
    snapshot_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    with connect(database_path) as connection:
        connection.execute(
            """INSERT INTO evidence_snapshots (id, name, as_of_date, values_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (snapshot_id, name, as_of, json.dumps(values, allow_nan=False), created_at),
        )
    return get_snapshot(database_path, snapshot_id)  # type: ignore[return-value]


def list_snapshots(database_path: Path, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    with connect(database_path) as connection:
        total = connection.execute("SELECT COUNT(*) FROM evidence_snapshots").fetchone()[0]
        rows = connection.execute(
            "SELECT * FROM evidence_snapshots ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [_snapshot_from_row(row) for row in rows], int(total)


def get_snapshot(database_path: Path, snapshot_id: str) -> dict[str, Any] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM evidence_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
    return _snapshot_from_row(row) if row else None


def _snapshot_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "as_of": row["as_of_date"],
        "values": json.loads(row["values_json"]),
        "created_at": row["created_at"],
    }
