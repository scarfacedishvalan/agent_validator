from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from jsonschema import FormatChecker, ValidationError, validate

from app.services.factor_view_prompts import (
    load_factor_view_output_contract,
    render_factor_view_system_prompt,
    render_factor_view_user_prompt,
)
from app.services.utils.aisuite_llm_client import AISuiteLLMClient, Message, Tool


BACKEND_DIR = Path(__file__).resolve().parents[3]
FIXTURES_DIR = BACKEND_DIR / "fixtures"
DEFAULT_SNAPSHOT_PATH = FIXTURES_DIR / "evidence_snapshot_example.json"
DEFAULTS_PATH = FIXTURES_DIR / "factor_view_defaults.json"
FACTOR_DEFINITIONS_PATH = FIXTURES_DIR / "factor_definitions.json"
METRIC_DEFINITIONS_PATH = FIXTURES_DIR / "metric_definitions.json"


class CompletionClient(Protocol):
    def complete(
        self,
        messages: Sequence[Message],
        *,
        tools: Sequence[Tool] | None = None,
    ) -> str: ...


def generate_factor_views(
    evidence_snapshot: Mapping[str, Any],
    *,
    model: str = "openai:gpt-4o",
    tools: Sequence[Tool] | None = None,
    llm_client: CompletionClient | None = None,
) -> dict[str, Any]:
    """Generate and validate factor views from a snapshot and workspace fixtures."""
    defaults = _read_json_object(DEFAULTS_PATH)
    factor_definitions = _read_json_array(FACTOR_DEFINITIONS_PATH)
    metric_definitions = _read_json_array(METRIC_DEFINITIONS_PATH)
    contract = load_factor_view_output_contract()

    system_prompt = render_factor_view_system_prompt(
        target_horizon=defaults["target_horizon"],
        q_return_convention=defaults["q_return_convention"],
        q_min=defaults["q_min"],
        q_max=defaults["q_max"],
        factor_definitions=factor_definitions,
        metric_definitions=metric_definitions,
    )
    system_prompt += "\n\nOUTPUT_JSON_SCHEMA:\n" + json.dumps(
        contract, ensure_ascii=False, indent=2, allow_nan=False
    )
    user_prompt = render_factor_view_user_prompt(
        target_horizon=defaults["target_horizon"],
        q_return_convention=defaults["q_return_convention"],
        q_min=defaults["q_min"],
        q_max=defaults["q_max"],
        factor_definitions=factor_definitions,
        metric_definitions=metric_definitions,
        evidence_snapshot=evidence_snapshot,
    )

    client = llm_client if llm_client is not None else AISuiteLLMClient(model=model)
    response_text = client.complete(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        tools=tools,
    )
    try:
        response = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("The LLM response was not valid JSON.") from exc
    if not isinstance(response, dict):
        raise ValueError("The LLM response must be a JSON object.")

    _validate_factor_view_response(
        response,
        contract=contract,
        evidence_snapshot=evidence_snapshot,
        target_horizon=defaults["target_horizon"],
        q_return_convention=defaults["q_return_convention"],
        factor_definitions=factor_definitions,
    )
    return response


def _validate_factor_view_response(
    response: dict[str, Any],
    *,
    contract: Mapping[str, Any],
    evidence_snapshot: Mapping[str, Any],
    target_horizon: str,
    q_return_convention: str,
    factor_definitions: Sequence[Mapping[str, Any]],
) -> None:
    try:
        validate(instance=response, schema=contract, format_checker=FormatChecker())
    except ValidationError as exc:
        raise ValueError(f"LLM response violates the factor-view output schema: {exc.message}") from exc

    factor_order = [factor["key"] for factor in factor_definitions]
    if response["factorOrder"] != factor_order:
        raise ValueError("LLM response factorOrder does not match the configured factor catalog.")
    if response["asOf"] != evidence_snapshot.get("asOf"):
        raise ValueError("LLM response asOf does not match the evidence snapshot.")
    if response["targetHorizon"] != target_horizon:
        raise ValueError("LLM response targetHorizon does not match the configured horizon.")
    if response["qReturnConvention"] != q_return_convention:
        raise ValueError("LLM response qReturnConvention does not match the configured convention.")

    assessments = response["factorAssessments"]
    if [item["factor"] for item in assessments] != factor_order:
        raise ValueError("LLM response must assess every configured factor in catalog order.")
    active_factors = [item["factor"] for item in assessments if item["status"] == "view"]
    if response["activeFactors"] != active_factors:
        raise ValueError("LLM response activeFactors must match its active assessments in catalog order.")

    expected_p = [
        [int(factor == active_factor) for factor in factor_order]
        for active_factor in active_factors
    ]
    expected_q = [
        [next(item["q"] for item in assessments if item["factor"] == active_factor)]
        for active_factor in active_factors
    ]
    if response["P"] != expected_p:
        raise ValueError("LLM response P must contain one matching one-hot row per active factor.")
    if response["Q"] != expected_q:
        raise ValueError("LLM response Q must contain the active assessment q values in the same order.")


def _read_json_object(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return value


def _read_json_array(path: Path) -> list[dict[str, Any]]:
    value = _read_json(path)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Expected an array of JSON objects in {path}.")
    return value


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate Black-Litterman factor views from an evidence snapshot.")
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=DEFAULT_SNAPSHOT_PATH,
        help="Path to a snapshot JSON file (defaults to the workspace example).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", "openai:gpt-4o"),
        help="AISuite provider:model identifier.",
    )
    args = parser.parse_args(argv)

    evidence_snapshot = _read_json_object(args.snapshot)
    response = generate_factor_views(evidence_snapshot, model=args.model)
    p_rows = [json.dumps(row, allow_nan=False) for row in response["P"]]
    p_display = "[\n    " + ",\n    ".join(p_rows) + "\n  ]" if p_rows else "[]"
    q_display = json.dumps(response["Q"], allow_nan=False)
    print('{\n  "P": ' + p_display + ',\n  "Q": ' + q_display + "\n}")


if __name__ == "__main__":
    main()
