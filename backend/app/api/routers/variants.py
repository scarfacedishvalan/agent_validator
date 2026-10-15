from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_database_path, get_metric_catalog_path
from app.db.repositories.variants import (
    create_variant_batch,
    get_variant,
    get_variant_batch,
    list_batch_variants,
)
from app.domain.mutations import (
    GENERATOR_VERSION,
    MutationValidationError,
    PREVIEW_LIMIT,
)
from app.schemas.mutations import (
    EvidenceVariant,
    VariantBatchResponse,
    VariantGenerateRequest,
    VariantGenerateResponse,
    VariantPreviewRequest,
    VariantPreviewResponse,
)
from app.services.workbench import (
    load_metric_catalog,
    preview_for_snapshot,
    resolve_generation_configuration,
    serialize_profile,
)

router = APIRouter(prefix="/api/v1/variants", tags=["variants"])


def _catalog(catalog_path: Path) -> list[dict]:
    try:
        return load_metric_catalog(catalog_path)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Metric catalog could not be loaded.") from exc


def _handle_mutation_error(error: MutationValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail={"issues": error.issues})


@router.post("/preview", response_model=VariantPreviewResponse)
def preview(
    payload: VariantPreviewRequest,
    database_path: Path = Depends(get_database_path),
    catalog_path: Path = Depends(get_metric_catalog_path),
) -> dict:
    try:
        result = preview_for_snapshot(database_path, _catalog(catalog_path), payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MutationValidationError as exc:
        raise _handle_mutation_error(exc) from exc
    return {**result.as_dict(), "preview_limit": PREVIEW_LIMIT}


@router.post(
    "/generate",
    response_model=VariantGenerateResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate(
    payload: VariantGenerateRequest,
    database_path: Path = Depends(get_database_path),
    catalog_path: Path = Depends(get_metric_catalog_path),
) -> dict:
    try:
        mutation_config, profile, result = resolve_generation_configuration(
            database_path,
            _catalog(catalog_path),
            payload,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MutationValidationError as exc:
        raise _handle_mutation_error(exc) from exc

    profile_snapshot = serialize_profile(profile) if profile else None
    try:
        return create_variant_batch(
            database_path,
            payload.snapshot_id,
            profile["id"] if profile else None,
            profile_snapshot,
            mutation_config,
            GENERATOR_VERSION,
            result.variants,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Variant batch could not be persisted.") from exc


@router.get("", response_model=VariantBatchResponse)
def get_batch(
    batch_id: str = Query(min_length=1),
    database_path: Path = Depends(get_database_path),
) -> dict:
    batch = get_variant_batch(database_path, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Variant batch not found.")
    return batch


@router.get("/{variant_id}", response_model=EvidenceVariant)
def get_variant_by_id(
    variant_id: str,
    database_path: Path = Depends(get_database_path),
) -> dict:
    variant = get_variant(database_path, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="Evidence variant not found.")
    return variant


@router.get("/batch/{batch_id}/variants", response_model=list[EvidenceVariant])
def get_batch_variants(
    batch_id: str,
    database_path: Path = Depends(get_database_path),
) -> list[dict]:
    variants = list_batch_variants(database_path, batch_id)
    if variants is None:
        raise HTTPException(status_code=404, detail="Variant batch not found.")
    return variants
