import unittest
from unittest.mock import patch

from app.services.mock_llm_client import MockLLMClient
from app.services.factor_view_prompts import load_factor_view_output_contract


PROMPT = '''EVIDENCE_SNAPSHOT_JSON:
{
  "asOf": "2026-10-01",
  "values": {
        "HML_return_12m": -0.2,
        "RMW_return_12m": 0.4,
        "MOM_return_12m": 0.1
  }
}
'''


class MockLLMClientTests(unittest.TestCase):
    def test_extract_value_returns_mean_absolute_value_without_noise(self):
        client = MockLLMClient(noise_std=0)
        self.assertAlmostEqual(client.extract_value(PROMPT), 0.7 / 3)

    def test_noise_is_reproducible_with_same_seed(self):
        first = MockLLMClient(noise_std=0.01, seed=23)
        second = MockLLMClient(noise_std=0.01, seed=23)
        self.assertEqual(first.complete(PROMPT), second.complete(PROMPT))

    def test_noise_is_small_and_centered_on_mean_absolute_value(self):
        client = MockLLMClient(noise_std=0.01, seed=3)
        result = client.extract_value(PROMPT)
        self.assertLess(abs(result - 0.7 / 3), 0.05)

    def test_complete_uses_contract_fixture_and_three_extracted_values(self):
        client = MockLLMClient(noise_std=0)
        contract_example = load_factor_view_output_contract()["example"]
        with patch.object(client, "extract_value", side_effect=[0.1, 0.2, 0.3]) as extract:
            result = client.complete(PROMPT)

        self.assertEqual(extract.call_count, 3)
        self.assertEqual(result["factorOrder"], contract_example["factorOrder"])
        self.assertEqual(result["P"], contract_example["P"])
        self.assertEqual(result["activeFactors"], contract_example["activeFactors"])
        self.assertEqual([item["q"] for item in result["factorAssessments"]], [0.1, 0.2, 0.3])
        self.assertEqual(result["Q"], [[0.1], [0.2], [0.3]])

    def test_rejects_negative_noise(self):
        with self.assertRaises(ValueError):
            MockLLMClient(noise_std=-0.01)


if __name__ == "__main__":
    unittest.main()
