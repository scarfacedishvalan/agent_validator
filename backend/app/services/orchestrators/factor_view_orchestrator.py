from __future__ import annotations

import argparse
from datetime import date
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from jsonschema import FormatChecker, ValidationError, validate

from app.services.factor_view_prompts import (
    DEFAULT_PERSONALITY_KEY,
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
    personality_key: str = DEFAULT_PERSONALITY_KEY,
    model: str = "openai:gpt-4o",
    tools: Sequence[Tool] | None = None,
    llm_client: CompletionClient | None = None,
) -> dict[str, Any]:
    """Generate validated factor views using a personality key from the fixtures."""
    defaults = _read_json_object(DEFAULTS_PATH)
    defaults["target_horizon"] = defaults["target_horizon"].strip()
    defaults["q_return_convention"] = defaults["q_return_convention"].strip()
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
        personality_key=personality_key,
    )

    return generate_from_messages(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        contract=contract,
        evidence_snapshot=evidence_snapshot,
        defaults=defaults,
        factor_definitions=factor_definitions,
        model=model,
        llm_client=llm_client,
        tools=tools,
    )


def generate_from_messages(
    messages: Sequence[Message],
    *,
    contract: Mapping[str, Any],
    evidence_snapshot: Mapping[str, Any],
    defaults: Mapping[str, Any],
    factor_definitions: Sequence[Mapping[str, Any]],
    model: str,
    llm_client: CompletionClient | None = None,
    tools: Sequence[Tool] | None = None,
) -> dict[str, Any]:
    """Execute already-rendered immutable messages without re-reading local files."""
    client = llm_client if llm_client is not None else AISuiteLLMClient(model=model)
    response_text = client.complete(messages, tools=tools)
    try:
        response = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("The LLM response was not valid JSON.") from exc
    if not isinstance(response, dict):
        raise ValueError("The LLM response must be a JSON object.")
    # Reject NaN/Infinity even when a permissive JSON decoder or schema accepts them.
    json.dumps(response, allow_nan=False)

    validate_factor_view_response(
        response,
        contract=contract,
        evidence_snapshot=evidence_snapshot,
        target_horizon=defaults["target_horizon"],
        q_return_convention=defaults["q_return_convention"],
        factor_definitions=factor_definitions,
    )
    for assessment in response["factorAssessments"]:
        if assessment["status"] == "view":
            q = assessment["q"]
            if isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(q):
                raise ValueError("Active Q values must be finite numbers.")
            if defaults.get("q_min") is not None and q < defaults["q_min"]:
                raise ValueError("Active Q is below the configured lower bound.")
            if defaults.get("q_max") is not None and q > defaults["q_max"]:
                raise ValueError("Active Q is above the configured upper bound.")
    return response


def validate_factor_view_response(
    response: dict[str, Any],
    *,
    contract: Mapping[str, Any],
    evidence_snapshot: Mapping[str, Any],
    target_horizon: str,
    q_return_convention: str,
    factor_definitions: Sequence[Mapping[str, Any]],
) -> None:
    required = ("factorOrder", "asOf", "targetHorizon", "qReturnConvention",
                "factorAssessments", "activeFactors", "P", "Q")
    if any(key not in response for key in required):
        raise ValueError("LLM response is missing required factor-view fields.")
    if not isinstance(response["asOf"], str):
        raise ValueError("LLM response asOf must be a date string.")
    date.fromisoformat(response["asOf"])
    if any(not isinstance(response[key], str) or not response[key].strip() for key in ("targetHorizon", "qReturnConvention")):
        raise ValueError("LLM response return context must contain non-blank strings.")
    if not isinstance(response["factorAssessments"], list):
        raise ValueError("LLM response factorAssessments must be an array.")
    for assessment in response["factorAssessments"]:
        if not isinstance(assessment, dict) or any(
            key not in assessment for key in ("factor", "status", "q", "confidence", "evidenceRefs", "rationale")
        ):
            raise ValueError("Every factor assessment must contain all required assessment fields.")
        if assessment["status"] not in ("view", "abstain"):
            raise ValueError("Assessment status must be view or abstain.")
        if not isinstance(assessment["rationale"], str) or not assessment["rationale"].strip():
            raise ValueError("Assessment rationale must be non-blank.")
        refs = assessment["evidenceRefs"]
        if not isinstance(refs, list) or not all(isinstance(ref, str) and ref.strip() for ref in refs) or len(set(refs)) != len(refs):
            raise ValueError("Assessment evidenceRefs must be an array of strings.")
        if assessment["status"] == "abstain":
            if assessment["q"] is not None or assessment["confidence"] is not None or refs:
                raise ValueError("Abstentions require null Q/confidence and no evidence references.")
        else:
            q = assessment["q"]
            if isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(q):
                raise ValueError("Active Q values must be finite numbers.")
            confidence = assessment["confidence"]
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise ValueError("Active confidence must be a number between zero and one.")
            if not refs or ("values" in evidence_snapshot and any(ref not in evidence_snapshot["values"] for ref in refs)):
                raise ValueError("Active assessments must reference supplied evidence keys.")
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
    if (
        response["P"] != expected_p
        or any(not isinstance(row, list) or any(type(item) is not int for item in row) for row in response["P"])
    ):
        raise ValueError("LLM response P must contain one matching one-hot row per active factor.")
    if (
        response["Q"] != expected_q
        or any(
            not isinstance(row, list) or len(row) != 1
            or isinstance(row[0], bool) or not isinstance(row[0], (int, float))
            for row in response["Q"]
        )
    ):
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
        "--personality",
        default=DEFAULT_PERSONALITY_KEY,
        help=f"Exact key from personalities.json (default: {DEFAULT_PERSONALITY_KEY}).",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", "openai:gpt-4o"),
        help="AISuite provider:model identifier.",
    )
    args = parser.parse_args(argv)

    evidence_snapshot = _read_json_object(args.snapshot)
    response = generate_factor_views(
        evidence_snapshot, personality_key=args.personality, model=args.model
    )
    p_rows = [json.dumps(row, allow_nan=False) for row in response["P"]]
    p_display = "[\n    " + ",\n    ".join(p_rows) + "\n  ]" if p_rows else "[]"
    q_display = json.dumps(response["Q"], allow_nan=False)
    print('{\n  "P": ' + p_display + ',\n  "Q": ' + q_display + "\n}")


if __name__ == "__main__":
    main()
