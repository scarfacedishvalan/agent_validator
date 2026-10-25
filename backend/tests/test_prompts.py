import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.factor_view_prompts import (
    DEFAULT_PERSONALITY_KEY,
    PERSONALITIES_PATH,
    SHARED_FINANCIAL_GROUNDING_POLICY_PATH,
    load_agent_personality,
    load_factor_view_output_contract,
    render_factor_view_system_prompt,
    render_factor_view_user_prompt,
)


class FactorViewPromptTests(unittest.TestCase):
    def test_loads_each_personality_as_instructions(self):
        personalities = json.loads(PERSONALITIES_PATH.read_text(encoding="utf-8"))
        self.assertIn(DEFAULT_PERSONALITY_KEY, personalities)
        for key, sentences in personalities.items():
            with self.subTest(personality_key=key):
                self.assertEqual(load_agent_personality(key), "\n".join(sentences))

    def test_rejects_unknown_and_blank_personality_keys(self):
        for key, message in [
            ("unknown", "Unknown personality key"),
            (" \n ", "personality_key must not be blank"),
        ]:
            with self.subTest(personality_key=key):
                with self.assertRaisesRegex(ValueError, message):
                    load_agent_personality(key)

    def test_rejects_malformed_personality_data(self):
        cases = [
            ([], "Personalities must be a JSON object"),
            ({"test": "not an array"}, "must be a non-empty array"),
            ({"test": []}, "must be a non-empty array"),
            ({"test": [""]}, "must be a non-empty array"),
            ({"test": [" \n "]}, "must be a non-empty array"),
            ({"test": ["valid", 1]}, "must be a non-empty array"),
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "personalities.json"
            for data, message in cases:
                with self.subTest(data=data):
                    path.write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        load_agent_personality("test", path)

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
        self.assertNotIn("{shared_financial_grounding_policy}", prompt)
        policy = SHARED_FINANCIAL_GROUNDING_POLICY_PATH.read_text(encoding="utf-8").strip()
        self.assertEqual(prompt.count(policy), 1)

    def test_system_policy_can_be_replaced_without_formatting_its_contents(self):
        policy = 'Replacement policy with literal braces: {"rule": "{target_horizon}"}'
        prompt = render_factor_view_system_prompt(
            target_horizon="12 months",
            q_return_convention="annualized excess return",
            q_min=None,
            q_max=None,
            factor_definitions=[],
            metric_definitions=[],
            shared_financial_grounding_policy=policy,
        )
        self.assertIn(policy, prompt)
        self.assertNotIn("SHARED FINANCIAL GROUNDING POLICY", prompt)
        self.assertNotIn("{shared_financial_grounding_policy}", prompt)
        self.assertIn("TARGET_HORIZON:\n12 months", prompt)

    def test_blank_system_policy_is_rejected(self):
        with self.assertRaisesRegex(
            ValueError, "shared_financial_grounding_policy must not be blank"
        ):
            render_factor_view_system_prompt(
                target_horizon="12 months",
                q_return_convention="annualized excess return",
                q_min=None,
                q_max=None,
                factor_definitions=[],
                metric_definitions=[],
                shared_financial_grounding_policy=" \n ",
            )

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
        self.assertNotIn("{agent_personality}", prompt)
        self.assertIn(DEFAULT_PERSONALITY_KEY, prompt)
        self.assertIn(load_agent_personality(DEFAULT_PERSONALITY_KEY), prompt)

    def test_renders_selected_personality_and_preserves_literal_braces(self):
        prompt = render_factor_view_user_prompt(
            target_horizon="12 months",
            q_return_convention="annualized excess return",
            q_min=None,
            q_max=None,
            factor_definitions=[],
            metric_definitions=[],
            evidence_snapshot={"values": {"literal": "{agent_personality}"}},
            personality_key="Contrarian Mean-Reversion Analyst",
        )
        self.assertIn(
            "AGENT PERSONALITY:\n\nContrarian Mean-Reversion Analyst\n"
            + load_agent_personality("Contrarian Mean-Reversion Analyst"),
            prompt,
        )
        self.assertNotIn(load_agent_personality(DEFAULT_PERSONALITY_KEY), prompt)
        self.assertIn('"literal": "{agent_personality}"', prompt)

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
