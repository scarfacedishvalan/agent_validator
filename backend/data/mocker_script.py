from __future__ import annotations

import json
import math
import re
from typing import Any


_EVIDENCE_SNAPSHOT_MARKER = re.compile(r"(?m)^EVIDENCE_SNAPSHOT_JSON:\s*")


def extract_evidence_values(prompt: str) -> dict[str, int | float]:
    """Extract the numeric ``values`` object from a rendered user prompt."""
    matches = list(_EVIDENCE_SNAPSHOT_MARKER.finditer(prompt))
    if len(matches) != 1:
        raise ValueError(
            "Prompt must contain exactly one EVIDENCE_SNAPSHOT_JSON section."
        )

    start = matches[0].end()
    while start < len(prompt) and prompt[start].isspace():
        start += 1

    try:
        snapshot: Any = json.JSONDecoder().raw_decode(prompt, start)[0]
    except json.JSONDecodeError as exc:
        raise ValueError("EVIDENCE_SNAPSHOT_JSON must contain valid JSON.") from exc

    if not isinstance(snapshot, dict):
        raise ValueError("EVIDENCE_SNAPSHOT_JSON must be a JSON object.")

    values = snapshot.get("values")
    if not isinstance(values, dict):
        raise ValueError("Evidence snapshot must contain a 'values' object.")

    for key, value in values.items():
        if not isinstance(key, str):
            raise ValueError("Evidence value keys must be strings.")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Evidence value '{key}' must be numeric.")
        if not math.isfinite(value):
            raise ValueError(f"Evidence value '{key}' must be finite.")

    return values
