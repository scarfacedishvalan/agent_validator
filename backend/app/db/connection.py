from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


_SCHEMA = """
CREATE TABLE IF NOT EXISTS evidence_snapshots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    values_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mutation_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    field_keys_json TEXT NOT NULL,
    settings_json TEXT NOT NULL,
    combination_mode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS variant_batches (
    id TEXT PRIMARY KEY,
    source_snapshot_id TEXT NOT NULL,
    profile_id TEXT,
    profile_snapshot_json TEXT,
    mutation_config_json TEXT NOT NULL,
    generator_version TEXT NOT NULL,
    total_generated INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_snapshot_id) REFERENCES evidence_snapshots(id),
    FOREIGN KEY(profile_id) REFERENCES mutation_profiles(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS evidence_variants (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    values_json TEXT NOT NULL,
    changed_fields_json TEXT NOT NULL,
    FOREIGN KEY(batch_id) REFERENCES variant_batches(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_variant_batches_snapshot
    ON variant_batches(source_snapshot_id, created_at);
CREATE INDEX IF NOT EXISTS idx_evidence_variants_batch
    ON evidence_variants(batch_id);
"""


@contextmanager
def connect(database_path: Path) -> Iterator[sqlite3.Connection]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: Path) -> None:
    with connect(database_path) as connection:
        connection.executescript(_SCHEMA)
