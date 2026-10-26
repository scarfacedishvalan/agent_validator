from copy import deepcopy
import unittest

from app.services.convergence_costs import estimate_call_cost, update_costs


class ConvergenceCostTests(unittest.TestCase):
    def setUp(self):
        self.pricing = {"rates": {
            "input": 2, "cachedInput": 0.2, "cacheWrite": 2.5, "output": 12,
            "maxInputTokens": 272000,
        }}
        self.call = {"iteration": 1, "usage": {
            "prompt_tokens": 1000, "completion_tokens": 100,
            "prompt_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 100},
            "completion_tokens_details": {"reasoning_tokens": 80},
        }}

    def test_separates_input_cache_reads_and_writes_without_double_counting_reasoning(self):
        cost = estimate_call_cost(self.call, self.pricing)
        self.assertAlmostEqual(cost["inputUsd"], 0.0014)
        self.assertAlmostEqual(cost["cachedInputUsd"], 0.00004)
        self.assertAlmostEqual(cost["cacheWriteUsd"], 0.00025)
        self.assertAlmostEqual(cost["outputUsd"], 0.0012)
        self.assertAlmostEqual(cost["estimatedUsd"], 0.00289)

    def test_zero_usage_is_a_real_zero_cost(self):
        self.call["usage"] = {"prompt_tokens": 0, "completion_tokens": 0}
        self.assertEqual(estimate_call_cost(self.call, self.pricing)["estimatedUsd"], 0)

    def test_missing_rates_usage_invalid_counts_and_unsupported_pricing_are_explicit(self):
        cases = [
            ({"iteration": 1, "usage": None}, self.pricing),
            (self.call, {"rates": None}),
            ({**self.call, "serviceTier": "priority"}, self.pricing),
            ({**self.call, "usage": {"prompt_tokens": True, "completion_tokens": 100}}, self.pricing),
            ({**self.call, "usage": {**self.call["usage"], "prompt_tokens": 272001}}, self.pricing),
            ({**self.call, "usage": {**self.call["usage"],
                                    "prompt_tokens_details": {"cached_tokens": 1001}}}, self.pricing),
            ({**self.call, "usage": {**self.call["usage"],
                                    "prompt_tokens_details": {"cache_write_tokens": -1}}}, self.pricing),
            (self.call, {"rates": {key: value for key, value in self.pricing["rates"].items()
                                  if key != "cacheWrite"}}),
        ]
        for call, pricing in cases:
            with self.subTest(call=call, pricing=pricing):
                cost = estimate_call_cost(call, pricing)
                self.assertIsNone(cost["estimatedUsd"])
                self.assertTrue(cost["reason"])

    def test_partial_total_does_not_misrepresent_missing_usage_as_zero(self):
        metadata = {"costs": {"pricing": deepcopy(self.pricing)},
                    "tokenUsage": {"calls": [self.call, {"iteration": 2, "usage": None}]}}
        update_costs(metadata)
        self.assertFalse(metadata["costs"]["complete"])
        self.assertAlmostEqual(metadata["costs"]["reportedTotalUsd"], 0.00289)
        metadata["tokenUsage"]["calls"] = [{"iteration": 1, "usage": None}]
        update_costs(metadata)
        self.assertIsNone(metadata["costs"]["reportedTotalUsd"])


if __name__ == "__main__":
    unittest.main()
