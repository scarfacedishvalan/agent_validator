from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.connection import connect
from app.domain.mutations import GeneratedVariant


def create_variant_batch(
    database_path: Path,
    snapshot_id: str,
    profile_id: str | None,
    profile_snapshot: dict[str, Any] | None,
    mutation_config: dict[str, Any],
    generator_version: str,
    variants: list[GeneratedVariant],
) -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    variant_ids = [str(uuid.uuid4()) for _ in variants]

    with connect(database_path) as connection:
        connection.execute(
            """INSERT INTO variant_batches
               (id, source_snapshot_id, profile_id, profile_snapshot_json,
                mutation_config_json, generator_version, total_generated, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                batch_id,
                snapshot_id,
                profile_id,
                json.dumps(profile_snapshot, allow_nan=False) if profile_snapshot else None,
                json.dumps(mutation_config, allow_nan=False),
                generator_version,
                len(variants),
                created_at,
            ),
        )
        connection.executemany(
            """INSERT INTO evidence_variants (id, batch_id, values_json, changed_fields_json)
               VALUES (?, ?, ?, ?)""",
            [
                (
                    variant_id,
                    batch_id,
                    json.dumps(variant.values, allow_nan=False),
                    json.dumps(variant.changed_fields),
                )
                for variant_id, variant in zip(variant_ids, variants)
            ],
        )

    return {
        "batch_id": batch_id,
        "variant_ids": variant_ids,
        "total_generated": len(variants),
        "generator_version": generator_version,
        "created_at": created_at,
    }


def get_variant_batch(database_path: Path, batch_id: str) -> dict[str, Any] | None:
    with connect(database_path) as connection:
        batch = connection.execute(
            "SELECT * FROM variant_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if batch is None:
            return None
        rows = connection.execute(
            "SELECT * FROM evidence_variants WHERE batch_id = ? ORDER BY rowid",
            (batch_id,),
        ).fetchall()

    return {
        "id": batch["id"],
        "snapshot_id": batch["source_snapshot_id"],
        "profile_id": batch["profile_id"],
        "profile_snapshot": json.loads(batch["profile_snapshot_json"])
        if batch["profile_snapshot_json"] else None,
        "mutation_config": json.loads(batch["mutation_config_json"]),
        "generator_version": batch["generator_version"],
        "total_generated": batch["total_generated"],
        "created_at": batch["created_at"],
        "variants": [_variant_from_row(row) for row in rows],
    }


def list_batch_variants(database_path: Path, batch_id: str) -> list[dict[str, Any]] | None:
    with connect(database_path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM variant_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if exists is None:
            return None
        rows = connection.execute(
            "SELECT * FROM evidence_variants WHERE batch_id = ? ORDER BY rowid",
            (batch_id,),
        ).fetchall()
    return [_variant_from_row(row) for row in rows]


def get_variant(database_path: Path, variant_id: str) -> dict[str, Any] | None:
    with connect(database_path) as connection:
        row = connection.execute(
            "SELECT * FROM evidence_variants WHERE id = ?", (variant_id,)
        ).fetchone()
    return _variant_from_row(row) if row else None


def _variant_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "values": json.loads(row["values_json"]),
        "changed_fields": json.loads(row["changed_fields_json"]),
    }
