from __future__ import annotations

import math
import random
from copy import deepcopy
from typing import Any

from data.mocker_script import extract_evidence_values
from app.services.factor_view_prompts import load_factor_view_output_contract


class MockLLMClient:
    """Return mean absolute prompt evidence with small Gaussian noise."""

    def __init__(self, noise_std: float = 0.01, seed: int | None = None) -> None:
        if not math.isfinite(noise_std) or noise_std < 0:
            raise ValueError("noise_std must be a finite, non-negative number.")
        self._noise_std = noise_std
        self._random = random.Random(seed)

    def extract_value(self, prompt: str) -> float:
        values = extract_evidence_values(prompt)
        if not values:
            raise ValueError("Evidence values must not be empty.")

        mean_absolute_value = math.fsum(abs(value) for value in values.values()) / len(values)
        noise = self._random.gauss(0.0, self._noise_std)
        return mean_absolute_value + noise

    def complete(self, prompt: str) -> dict[str, Any]:
        """Build the contract response with one independently sampled q per factor."""
        response = deepcopy(load_factor_view_output_contract()["example"])
        assessments = response["factorAssessments"]
        q_values = [self.extract_value(prompt) for _ in assessments]

        for assessment, q_value in zip(assessments, q_values):
            assessment["q"] = q_value

        response["Q"] = [[q_value] for q_value in q_values]
        return response
