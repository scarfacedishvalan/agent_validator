from __future__ import annotations

from decimal import Decimal
from typing import Any


def estimate_call_cost(call: dict[str, Any], pricing: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"iteration": call["iteration"], "estimatedUsd": None, "reason": None}
    rates = pricing["rates"]
    usage = call.get("usage")
    if rates is None:
        result["reason"] = "No pricing configured for the selected model."
        return result
    if not isinstance(usage, dict) or any(
        type(usage.get(key)) is not int or usage[key] < 0
        for key in ("prompt_tokens", "completion_tokens")
    ):
        result["reason"] = "Provider token usage is missing or invalid."
        return result
    if call.get("serviceTier") not in (None, "default", "standard"):
        result["reason"] = "Only standard service-tier pricing is configured."
        return result
    prompt, output = usage["prompt_tokens"], usage["completion_tokens"]
    details = usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict):
        result["reason"] = "Provider prompt token details are invalid."
        return result
    cached = details.get("cached_tokens", 0)
    written = details.get("cache_write_tokens", usage.get("cache_write_tokens", 0))
    if type(cached) is not int or not 0 <= cached <= prompt:
        result["reason"] = "Provider cached token count is invalid."
        return result
    if prompt > rates["maxInputTokens"]:
        result["reason"] = "Input exceeds the configured pricing context limit."
        return result
    if type(written) is not int or not 0 <= written <= prompt - cached:
        result["reason"] = "Provider cache-write token count is invalid."
        return result
    if written and "cacheWrite" not in rates:
        result["reason"] = "Cache-write pricing is not configured."
        return result
    breakdown = {
        "inputUsd": Decimal(prompt - cached - written) * Decimal(str(rates["input"])) / 1_000_000,
        "cachedInputUsd": Decimal(cached) * Decimal(str(rates["cachedInput"])) / 1_000_000,
        "cacheWriteUsd": Decimal(written) * Decimal(str(rates.get("cacheWrite", 0))) / 1_000_000,
        "outputUsd": Decimal(output) * Decimal(str(rates["output"])) / 1_000_000,
    }
    return {**result, **{key: float(value) for key, value in breakdown.items()},
            "estimatedUsd": float(sum(breakdown.values()))}


def update_costs(metadata: dict[str, Any]) -> None:
    costs = metadata["costs"]
    costs["iterations"] = [
        estimate_call_cost(call, costs["pricing"]) for call in metadata["tokenUsage"]["calls"]
    ]
    available = [Decimal(str(call["estimatedUsd"])) for call in costs["iterations"]
                 if call["estimatedUsd"] is not None]
    costs["reportedTotalUsd"] = float(sum(available)) if available else None
    costs["complete"] = len(available) == len(costs["iterations"])
