import unittest

from data.mocker_script import extract_evidence_values


class ExtractEvidenceValuesTests(unittest.TestCase):
    def test_extracts_numeric_values_from_prompt_section(self):
        prompt = '''Prompt context with unrelated braces: {"ignored": true}
EVIDENCE_SNAPSHOT_JSON:
{
  "asOf": "2026-10-01",
  "values": {
    "HML_return_12m": -0.045,
    "HML_valuation_zscore": 1.6
  },
  "metadata": {"source": "sample"}
}
'''
        self.assertEqual(
            extract_evidence_values(prompt),
            {"HML_return_12m": -0.045, "HML_valuation_zscore": 1.6},
        )

    def test_requires_one_snapshot_section(self):
        with self.assertRaises(ValueError):
            extract_evidence_values("No evidence section")

        duplicate = "EVIDENCE_SNAPSHOT_JSON: {}\nEVIDENCE_SNAPSHOT_JSON: {}"
        with self.assertRaises(ValueError):
            extract_evidence_values(duplicate)

    def test_rejects_non_numeric_evidence(self):
        prompt = 'EVIDENCE_SNAPSHOT_JSON: {"values": {"bad": true}}'
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            extract_evidence_values(prompt)


if __name__ == "__main__":
    unittest.main()
