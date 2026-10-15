from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.db.repositories import evidence_snapshots, mutation_profiles
from app.domain.mutations import (
    GENERATOR_VERSION,
    MAX_GENERATED_VARIANTS,
    PREVIEW_LIMIT,
    MutationValidationError,
    VariantResult,
    preview_variants,
    validate_mutation,
)
from app.schemas.evidence import MetricDefinition
from app.schemas.mutations import MutationSettings, VariantGenerateRequest, VariantPreviewRequest


def load_metric_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    raw_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw_catalog, list):
        raise ValueError("Metric catalog must be a JSON list.")
    definitions = [MetricDefinition.model_validate(item) for item in raw_catalog]
    keys = [definition.key for definition in definitions]
    if len(set(keys)) != len(keys):
        raise ValueError("Metric catalog contains duplicate keys.")
    return [definition.model_dump() for definition in definitions]


def metric_map(catalog: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(definition["key"]): definition for definition in catalog}


def validate_profile_shape(
    field_keys: Sequence[str],
    settings: MutationSettings,
    combination_mode: str,
    catalog: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    synthetic_values = {key: 0.0 for key in field_keys}
    return validate_mutation(
        field_keys,
        settings.model_dump(),
        combination_mode,
        synthetic_values,
        metric_map(catalog),
    )


def validate_profile_for_snapshot(
    profile: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    catalog: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    settings = profile["settings"]
    if isinstance(settings, MutationSettings):
        settings = settings.model_dump()
    return validate_mutation(
        profile["field_keys"],
        settings,
        profile["combination_mode"],
        snapshot["values"],
        metric_map(catalog),
    )


def preview_for_snapshot(
    database_path: Path,
    catalog: Sequence[Mapping[str, Any]],
    request: VariantPreviewRequest,
) -> VariantResult:
    snapshot = evidence_snapshots.get_snapshot(database_path, request.snapshot_id)
    if snapshot is None:
        raise LookupError(f"Snapshot '{request.snapshot_id}' was not found.")
    return preview_variants(
        snapshot["values"],
        request.field_keys,
        request.settings.model_dump(),
        request.combination_mode,
        metric_map(catalog),
        limit=PREVIEW_LIMIT,
    )


def resolve_generation_configuration(
    database_path: Path,
    catalog: Sequence[Mapping[str, Any]],
    request: VariantGenerateRequest,
) -> tuple[dict[str, Any], dict[str, Any] | None, VariantResult]:
    snapshot = evidence_snapshots.get_snapshot(database_path, request.snapshot_id)
    if snapshot is None:
        raise LookupError(f"Snapshot '{request.snapshot_id}' was not found.")

    profile: dict[str, Any] | None = None
    if request.profile_id:
        profile = mutation_profiles.get_profile(database_path, request.profile_id)
        if profile is None:
            raise LookupError(f"Mutation profile '{request.profile_id}' was not found.")

    field_keys = request.field_keys or (profile["field_keys"] if profile else [])
    settings_model = request.settings or (
        MutationSettings.model_validate(profile["settings"]) if profile else None
    )
    combination_mode = request.combination_mode or (
        profile["combination_mode"] if profile else None
    )
    if settings_model is None or combination_mode is None:
        raise MutationValidationError([{
            "code": "configuration_required",
            "message": "A complete mutation profile or inline configuration is required.",
        }])

    result = preview_variants(
        snapshot["values"],
        field_keys,
        settings_model.model_dump(),
        combination_mode,
        metric_map(catalog),
        limit=MAX_GENERATED_VARIANTS,
    )
    mutation_config = {
        "snapshot_id": request.snapshot_id,
        "field_keys": list(field_keys),
        "settings": settings_model.model_dump(mode="json"),
        "combination_mode": combination_mode,
    }
    return mutation_config, profile, result


def serialize_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    settings = profile["settings"]
    if isinstance(settings, MutationSettings):
        settings = settings.model_dump()
    return {
        "id": profile.get("id"),
        "name": profile["name"],
        "field_keys": list(profile["field_keys"]),
        "settings": settings,
        "combination_mode": profile["combination_mode"],
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
    }


def generation_version() -> str:
    return GENERATOR_VERSION
