from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

PREVIEW_LIMIT = 100
MAX_VALUES_PER_FIELD = 1_000
MAX_GENERATED_VARIANTS = 10_000
GENERATOR_VERSION = "1"


class MutationValidationError(ValueError):
    def __init__(self, issues: list[dict[str, str]]) -> None:
        self.issues = issues
        super().__init__("Mutation configuration is invalid.")


@dataclass(frozen=True)
class GeneratedVariant:
    id: str
    values: dict[str, float]
    changed_fields: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "values": self.values,
            "changedFields": self.changed_fields,
        }


@dataclass(frozen=True)
class VariantResult:
    variants: list[GeneratedVariant]
    total_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "variants": [variant.as_dict() for variant in self.variants],
            "totalCount": self.total_count,
        }


def validate_mutation(
    field_keys: Sequence[str],
    settings: Mapping[str, Any],
    combination_mode: str,
    snapshot_values: Mapping[str, float],
    metric_definitions: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    strategy = settings.get("strategy")

    if not field_keys:
        issues.append({"code": "fields_required", "message": "Select at least one evidence field."})

    if len(set(field_keys)) != len(field_keys):
        issues.append({"code": "duplicate_fields", "message": "Evidence fields must not be repeated."})

    selected_definitions: list[Mapping[str, Any]] = []
    for key in field_keys:
        definition = metric_definitions.get(key)
        if key not in snapshot_values:
            issues.append({"code": "field_missing", "field": key, "message": f"Field '{key}' is not present in this snapshot."})
        elif definition is None:
            issues.append({"code": "metric_unknown", "field": key, "message": f"Field '{key}' has no metric definition."})
        elif not definition.get("mutationEligible", definition.get("mutation_eligible", False)):
            issues.append({"code": "field_ineligible", "field": key, "message": f"Field '{key}' is not eligible for mutation."})
        else:
            selected_definitions.append(definition)

    units = {
        definition.get("unit")
        for definition in selected_definitions
        if definition.get("unit") is not None
    }
    if len(units) > 1:
        issues.append({"code": "mixed_units", "message": "Select fields with the same unit."})

    if combination_mode not in {"one-at-a-time", "cartesian"}:
        issues.append({"code": "combination_mode_invalid", "message": "Combination mode must be 'one-at-a-time' or 'cartesian'."})

    if strategy not in {"explicit", "range", "random"}:
        issues.append({"code": "strategy_invalid", "message": "Strategy must be 'explicit', 'range', or 'random'."})
    elif strategy == "explicit":
        values = settings.get("explicit_values", settings.get("explicitValues", []))
        if not isinstance(values, list) or not values:
            issues.append({"code": "explicit_values_required", "message": "Add at least one explicit value."})
        elif len(values) > MAX_VALUES_PER_FIELD:
            issues.append({"code": "too_many_values", "message": f"Use no more than {MAX_VALUES_PER_FIELD} values per field."})
        elif any(not _is_finite_number(value) for value in values):
            issues.append({"code": "explicit_values_invalid", "message": "Explicit values must be finite numbers."})
    elif strategy == "range":
        start = _setting_number(settings, "range_start", "rangeStart")
        end = _setting_number(settings, "range_end", "rangeEnd")
        step = _setting_number(settings, "range_step", "rangeStep")
        if start is None or end is None or step is None:
            issues.append({"code": "range_invalid", "message": "Range start, end, and step must be finite numbers."})
        elif step <= 0 or end < start:
            issues.append({"code": "range_invalid", "message": "Use a positive step and an end value greater than or equal to the start."})
        else:
            count = _range_count(start, end, step)
            if count > MAX_VALUES_PER_FIELD:
                issues.append({"code": "too_many_values", "message": f"A range may generate no more than {MAX_VALUES_PER_FIELD} values per field."})
    elif strategy == "random":
        spread = _setting_number(settings, "random_spread", "randomSpread")
        count = _setting_number(settings, "random_count", "randomCount")
        seed = _setting_number(settings, "seed")
        if spread is None or count is None or seed is None:
            issues.append({"code": "random_invalid", "message": "Random settings must be finite numbers."})
        elif spread < 0 or not count.is_integer() or count < 1 or count > MAX_VALUES_PER_FIELD:
            issues.append({"code": "random_invalid", "message": f"Use a non-negative spread and 1 to {MAX_VALUES_PER_FIELD} whole-number samples."})
        elif not seed.is_integer():
            issues.append({"code": "seed_invalid", "message": "Random seed must be a whole number."})

    return issues


def preview_variants(
    snapshot_values: Mapping[str, float],
    field_keys: Sequence[str],
    settings: Mapping[str, Any],
    combination_mode: str,
    metric_definitions: Mapping[str, Mapping[str, Any]],
    limit: int = PREVIEW_LIMIT,
) -> VariantResult:
    issues = validate_mutation(
        field_keys, settings, combination_mode, snapshot_values, metric_definitions
    )
    if issues:
        raise MutationValidationError(issues)

    value_grids = _value_grids(snapshot_values, field_keys, settings, metric_definitions)
    counts = [len(grid) for grid in value_grids]
    total_count = sum(counts) if combination_mode == "one-at-a-time" else math.prod(counts)
    if total_count > MAX_GENERATED_VARIANTS and limit > PREVIEW_LIMIT:
        raise MutationValidationError([{
            "code": "generation_limit_exceeded",
            "message": f"Generation is limited to {MAX_GENERATED_VARIANTS} variants; this profile would create {total_count}.",
        }])

    variants: list[GeneratedVariant] = []
    if combination_mode == "one-at-a-time":
        for field_key, values in zip(field_keys, value_grids):
            for value in values:
                if len(variants) >= limit:
                    break
                variants.append(_variant(len(variants), snapshot_values, {field_key: value}, [field_key]))
            if len(variants) >= limit:
                break
    else:
        for combination in itertools.islice(itertools.product(*value_grids), limit):
            changes = dict(zip(field_keys, combination))
            variants.append(_variant(len(variants), snapshot_values, changes, list(field_keys)))

    return VariantResult(variants=variants, total_count=total_count)


def _variant(
    index: int,
    snapshot_values: Mapping[str, float],
    changes: Mapping[str, float],
    changed_fields: list[str],
) -> GeneratedVariant:
    values = {key: float(value) for key, value in snapshot_values.items()}
    values.update(changes)
    return GeneratedVariant(
        id=f"variant-{index + 1}",
        values=values,
        changed_fields=changed_fields,
    )


def _value_grids(
    snapshot_values: Mapping[str, float],
    field_keys: Sequence[str],
    settings: Mapping[str, Any],
    metric_definitions: Mapping[str, Mapping[str, Any]],
) -> list[list[float]]:
    strategy = settings["strategy"]
    randomizer = random.Random(int(_setting_number(settings, "seed") or 0))
    grids: list[list[float]] = []

    for field_key in field_keys:
        definition = metric_definitions[field_key]
        scale = float(definition.get("displayScale", definition.get("display_scale", 1)) or 1)
        if scale == 0:
            scale = 1
        if strategy == "explicit":
            display_values = settings.get("explicit_values", settings.get("explicitValues", []))
            grid = [float(value) / scale for value in display_values]
        elif strategy == "range":
            start = _setting_number(settings, "range_start", "rangeStart")
            end = _setting_number(settings, "range_end", "rangeEnd")
            step = _setting_number(settings, "range_step", "rangeStep")
            assert start is not None and end is not None and step is not None
            count = _range_count(start, end, step)
            grid = [float(Decimal(str(start)) + Decimal(str(step)) * index) / scale for index in range(count)]
        else:
            spread = _setting_number(settings, "random_spread", "randomSpread")
            count = _setting_number(settings, "random_count", "randomCount")
            assert spread is not None and count is not None
            baseline = float(snapshot_values[field_key]) * scale
            grid = [
                round((baseline + (randomizer.random() * 2 - 1) * spread) / scale, 6)
                for _ in range(int(count))
            ]
        grids.append(grid)

    return grids


def _range_count(start: float, end: float, step: float) -> int:
    distance = Decimal(str(end)) - Decimal(str(start))
    increment = Decimal(str(step))
    return int(distance // increment) + 1


def _setting_number(settings: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in settings:
            value = settings[key]
            if _is_finite_number(value):
                return float(value)
            return None
    return None


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
