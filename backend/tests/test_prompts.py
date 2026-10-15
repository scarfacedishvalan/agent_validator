import json
from pathlib import Path
import unittest

from app.services.factor_view_prompts import (
    load_factor_view_output_contract,
    render_factor_view_system_prompt,
    render_factor_view_user_prompt,
)


class FactorViewPromptTests(unittest.TestCase):
    def test_factor_view_defaults_fixture(self):
        defaults_path = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "factor_view_defaults.json"
        )
        defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(defaults),
            {"target_horizon", "q_return_convention", "q_min", "q_max"},
        )
        self.assertEqual(defaults["target_horizon"], "12 months")
        self.assertEqual(defaults["q_return_convention"], "annualized excess return")
        self.assertIsNone(defaults["q_min"])
        self.assertIsNone(defaults["q_max"])

    def test_renders_system_template_without_unresolved_placeholders(self):
        prompt = render_factor_view_system_prompt(
            target_horizon="12 months",
            q_return_convention="annualized excess return",
            q_min=-0.2,
            q_max=0.2,
            factor_definitions=[{"key": "HML", "description": "Value factor"}],
            metric_definitions=[{"key": "HML_return_12m", "unit": "%"}],
        )
        self.assertIn("RUNTIME CONFIGURATION\n\nTARGET_HORIZON:\n12 months", prompt)
        self.assertIn('"key": "HML"', prompt)
        self.assertIn('"HML_return_12m"', prompt)
        self.assertNotIn("{target_horizon}", prompt)
        self.assertNotIn("{factor_definitions_json}", prompt)

    def test_loads_output_schema_and_example(self):
        contract = load_factor_view_output_contract()
        example = contract["example"]
        self.assertEqual(example["factorOrder"], ["HML", "RMW", "MOM"])
        self.assertEqual(len(example["P"]), 3)
        self.assertEqual(len(example["Q"]), 3)
        self.assertEqual(contract["properties"]["Q"]["type"], "array")

    def test_renders_context_for_client_without_unresolved_placeholders(self):
        prompt = render_factor_view_user_prompt(
            target_horizon="12 months",
            q_return_convention="annualized excess return",
            q_min=-0.2,
            q_max=0.2,
            factor_definitions=[{"key": "HML", "description": "Value factor"}],
            metric_definitions=[{"key": "HML_return_12m", "unit": "%"}],
            evidence_snapshot={"asOf": "2026-10-01", "values": {"HML_return_12m": 0.04}},
        )
        self.assertIn("TARGET_HORIZON:\n12 months", prompt)
        self.assertIn('"key": "HML"', prompt)
        self.assertIn('"HML_return_12m": 0.04', prompt)
        self.assertIn("Q_MIN", prompt)
        self.assertNotIn("{target_horizon}", prompt)
        self.assertNotIn("{evidence_snapshot_json}", prompt)

    def test_missing_runtime_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            render_factor_view_user_prompt(
                target_horizon=" ",
                q_return_convention="total return",
                q_min=None,
                q_max=None,
                factor_definitions=[],
                metric_definitions=[],
                evidence_snapshot={},
            )


if __name__ == "__main__":
    unittest.main()
