from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


USER_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "user_prompt.txt"
SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "system_prompt.txt"
PERSONALITIES_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "personalities.json"
DEFAULT_PERSONALITY_KEY = "Trend-Following Analyst"
SHARED_FINANCIAL_GROUNDING_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "prompts"
    / "shared_financial_grounding_policy.txt"
)
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


def load_agent_personality(
    personality_key: str,
    personalities_path: Path = PERSONALITIES_PATH,
) -> str:
    """Resolve a personality key to its newline-separated instructions."""
    if not personality_key.strip():
        raise ValueError("personality_key must not be blank.")
    personalities = json.loads(personalities_path.read_text(encoding="utf-8"))
    if not isinstance(personalities, dict):
        raise ValueError("Personalities must be a JSON object keyed by personality name.")
    if personality_key not in personalities:
        available = ", ".join(personalities)
        raise ValueError(
            f"Unknown personality key {personality_key!r}. Available keys: {available}."
        )
    sentences = personalities[personality_key]
    if (
        not isinstance(sentences, list)
        or not sentences
        or not all(isinstance(sentence, str) and sentence.strip() for sentence in sentences)
    ):
        raise ValueError(
            f"Personality {personality_key!r} must be a non-empty array of non-blank strings."
        )
    return "\n".join(sentence.strip() for sentence in sentences)


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
    personality_key: str = DEFAULT_PERSONALITY_KEY,
    template_text: str | None = None,
    personality_instructions: str | None = None,
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
    values["agent_personality"] = (
        personality_key + "\n" + (
            load_agent_personality(personality_key)
            if personality_instructions is None else personality_instructions
        )
    )
    values["evidence_snapshot_json"] = _to_json(evidence_snapshot)
    return render_template_text(template_text, values) if template_text is not None else _render_template(template_path, values)


def render_factor_view_system_prompt(
    *,
    target_horizon: str,
    q_return_convention: str,
    q_min: float | None,
    q_max: float | None,
    factor_definitions: Sequence[Mapping[str, Any]],
    metric_definitions: Sequence[Mapping[str, Any]],
    template_path: Path = SYSTEM_PROMPT_PATH,
    shared_financial_grounding_policy: str | None = None,
    template_text: str | None = None,
) -> str:
    """Render the system template with runtime inputs and a replaceable policy."""
    values = _runtime_template_values(
        target_horizon,
        q_return_convention,
        q_min,
        q_max,
        factor_definitions,
        metric_definitions,
    )
    policy = (
        SHARED_FINANCIAL_GROUNDING_POLICY_PATH.read_text(encoding="utf-8")
        if shared_financial_grounding_policy is None
        else shared_financial_grounding_policy
    ).strip()
    if not policy:
        raise ValueError("shared_financial_grounding_policy must not be blank.")
    values["shared_financial_grounding_policy"] = policy
    return render_template_text(template_text, values) if template_text is not None else _render_template(template_path, values)


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
    return render_template_text(template_path.read_text(encoding="utf-8"), values)


def render_template_text(template: str, values: Mapping[str, str]) -> str:
    try:
        return template.format_map(values).strip()
    except (KeyError, IndexError, AttributeError, ValueError) as exc:
        raise ValueError(f"Prompt template could not be rendered: {exc}") from exc


def _format_bound(value: float | None) -> str:
    if value is None:
        return "not configured"
    return json.dumps(value, allow_nan=False)


def _to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
