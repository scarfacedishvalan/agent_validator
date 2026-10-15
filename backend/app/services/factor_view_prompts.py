from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


USER_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "user_prompt.txt"
SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "system_prompt.txt"
OUTPUT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "factor_view_output_contract.json"
)


def load_factor_view_output_contract(
    contract_path: Path = OUTPUT_CONTRACT_PATH,
) -> dict[str, Any]:
    """Load the JSON Schema and example used to constrain factor-view output."""
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or not isinstance(contract.get("properties"), dict):
        raise ValueError("Factor-view output contract must be a JSON Schema object.")
    return contract


def render_factor_view_user_prompt(
    *,
    target_horizon: str,
    q_return_convention: str,
    q_min: float | None,
    q_max: float | None,
    factor_definitions: Sequence[Mapping[str, Any]],
    metric_definitions: Sequence[Mapping[str, Any]],
    evidence_snapshot: Mapping[str, Any],
    template_path: Path = USER_PROMPT_PATH,
) -> str:
    if not target_horizon.strip():
        raise ValueError("target_horizon must not be blank.")
    if not q_return_convention.strip():
        raise ValueError("q_return_convention must not be blank.")

    values = _runtime_template_values(
        target_horizon,
        q_return_convention,
        q_min,
        q_max,
        factor_definitions,
        metric_definitions,
    )
    values["evidence_snapshot_json"] = _to_json(evidence_snapshot)
    return _render_template(template_path, values)


def render_factor_view_system_prompt(
    *,
    target_horizon: str,
    q_return_convention: str,
    q_min: float | None,
    q_max: float | None,
    factor_definitions: Sequence[Mapping[str, Any]],
    metric_definitions: Sequence[Mapping[str, Any]],
    template_path: Path = SYSTEM_PROMPT_PATH,
) -> str:
    """Render the system-message template with runtime configuration and catalogs."""
    values = _runtime_template_values(
        target_horizon,
        q_return_convention,
        q_min,
        q_max,
        factor_definitions,
        metric_definitions,
    )
    return _render_template(template_path, values)


def _runtime_template_values(
    target_horizon: str,
    q_return_convention: str,
    q_min: float | None,
    q_max: float | None,
    factor_definitions: Sequence[Mapping[str, Any]],
    metric_definitions: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    if not target_horizon.strip():
        raise ValueError("target_horizon must not be blank.")
    if not q_return_convention.strip():
        raise ValueError("q_return_convention must not be blank.")
    return {
        "target_horizon": target_horizon.strip(),
        "q_return_convention": q_return_convention.strip(),
        "q_min": _format_bound(q_min),
        "q_max": _format_bound(q_max),
        "factor_definitions_json": _to_json(factor_definitions),
        "metric_definitions_json": _to_json(metric_definitions),
    }


def _render_template(template_path: Path, values: Mapping[str, str]) -> str:
    template = template_path.read_text(encoding="utf-8")
    try:
        return template.format_map(values).strip()
    except KeyError as exc:
        raise ValueError(f"Prompt template has an unknown placeholder: {exc.args[0]}") from exc


def _format_bound(value: float | None) -> str:
    if value is None:
        return "not configured"
    return json.dumps(value, allow_nan=False)


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
