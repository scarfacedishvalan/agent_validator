from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_database_path, get_metric_catalog_path
from app.db.repositories import evidence_snapshots, mutation_profiles
from app.schemas.mutations import (
    MutationProfileCreate,
    MutationProfileList,
    MutationProfileResponse,
    MutationProfileUpdate,
    MutationProfileValidation,
)
from app.services.workbench import (
    load_metric_catalog,
    serialize_profile,
    validate_profile_for_snapshot,
    validate_profile_shape,
)

router = APIRouter(prefix="/api/v1/mutation-profiles", tags=["mutation profiles"])


def _validate_shape(payload: MutationProfileCreate | MutationProfileUpdate, catalog_path: Path) -> None:
    try:
        catalog = load_metric_catalog(catalog_path)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Metric catalog could not be loaded.") from exc
    issues = validate_profile_shape(
        payload.field_keys,
        payload.settings,
        payload.combination_mode,
        catalog,
    )
    if issues:
        raise HTTPException(status_code=422, detail={"issues": issues})


@router.get("", response_model=MutationProfileList)
def get_profiles(database_path: Path = Depends(get_database_path)) -> dict:
    profiles, total = mutation_profiles.list_profiles(database_path)
    return {"profiles": profiles, "total": total}


@router.post(
    "",
    response_model=MutationProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_profile(
    payload: MutationProfileCreate,
    database_path: Path = Depends(get_database_path),
    catalog_path: Path = Depends(get_metric_catalog_path),
) -> dict:
    _validate_shape(payload, catalog_path)
    return mutation_profiles.create_profile(
        database_path,
        payload.name,
        payload.field_keys,
        payload.settings.model_dump(mode="json"),
        payload.combination_mode,
    )


@router.get("/{profile_id}", response_model=MutationProfileResponse)
def get_profile(
    profile_id: str,
    database_path: Path = Depends(get_database_path),
) -> dict:
    profile = mutation_profiles.get_profile(database_path, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Mutation profile not found.")
    return profile


@router.put("/{profile_id}", response_model=MutationProfileResponse)
def put_profile(
    profile_id: str,
    payload: MutationProfileUpdate,
    database_path: Path = Depends(get_database_path),
    catalog_path: Path = Depends(get_metric_catalog_path),
) -> dict:
    _validate_shape(payload, catalog_path)
    profile = mutation_profiles.update_profile(
        database_path,
        profile_id,
        payload.name,
        payload.field_keys,
        payload.settings.model_dump(mode="json"),
        payload.combination_mode,
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Mutation profile not found.")
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_profile(
    profile_id: str,
    database_path: Path = Depends(get_database_path),
) -> Response:
    if not mutation_profiles.delete_profile(database_path, profile_id):
        raise HTTPException(status_code=404, detail="Mutation profile not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{profile_id}/validate", response_model=MutationProfileValidation)
def validate_profile(
    profile_id: str,
    snapshot_id: str = Query(min_length=1),
    database_path: Path = Depends(get_database_path),
    catalog_path: Path = Depends(get_metric_catalog_path),
) -> dict:
    profile = mutation_profiles.get_profile(database_path, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Mutation profile not found.")
    snapshot = evidence_snapshots.get_snapshot(database_path, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Evidence snapshot not found.")
    try:
        issues = validate_profile_for_snapshot(profile, snapshot, load_metric_catalog(catalog_path))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Metric catalog could not be loaded.") from exc
    return {"compatible": not issues, "issues": issues}
