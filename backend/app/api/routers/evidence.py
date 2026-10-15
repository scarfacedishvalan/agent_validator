from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_database_path, get_metric_catalog_path
from app.db.repositories.evidence_snapshots import (
    create_snapshot,
    get_snapshot,
    list_snapshots,
)
from app.schemas.evidence import (
    EvidenceSnapshotCreate,
    EvidenceSnapshotList,
    EvidenceSnapshotResponse,
    MetricDefinition,
)
from app.services.workbench import load_metric_catalog

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@router.get("/snapshots", response_model=EvidenceSnapshotList)
def get_snapshots(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    database_path: Path = Depends(get_database_path),
) -> dict:
    snapshots, total = list_snapshots(database_path, limit, offset)
    return {"snapshots": snapshots, "total": total}


@router.post(
    "/snapshots",
    response_model=EvidenceSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_snapshot(
    payload: EvidenceSnapshotCreate,
    database_path: Path = Depends(get_database_path),
) -> dict:
    return create_snapshot(
        database_path,
        payload.name,
        payload.as_of.isoformat(),
        {key: float(value) for key, value in payload.values.items()},
    )


@router.get("/snapshots/{snapshot_id}", response_model=EvidenceSnapshotResponse)
def get_snapshot_by_id(
    snapshot_id: str,
    database_path: Path = Depends(get_database_path),
) -> dict:
    snapshot = get_snapshot(database_path, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evidence snapshot not found.")
    return snapshot


@router.get("/metrics", response_model=list[MetricDefinition])
def get_metrics(catalog_path: Path = Depends(get_metric_catalog_path)) -> list[dict]:
    try:
        return load_metric_catalog(catalog_path)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Metric catalog could not be loaded.") from exc
