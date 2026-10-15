import unittest

from app.domain.mutations import (
    MutationValidationError,
    preview_variants,
)


SNAPSHOT = {"factor_a": 0.1, "factor_b": 0.2}
METRICS = {
    "factor_a": {"unit": "%", "displayScale": 100, "mutationEligible": True},
    "factor_b": {"unit": "%", "displayScale": 100, "mutationEligible": True},
    "zscore": {"unit": "z-score", "displayScale": 1, "mutationEligible": True},
    "locked": {"unit": "%", "displayScale": 100, "mutationEligible": False},
}


def settings(strategy="explicit", **overrides):
    values = {
        "strategy": strategy,
        "explicit_values": [1.0, 2.0],
        "range_start": 0.0,
        "range_end": 1.0,
        "range_step": 0.5,
        "random_spread": 0.5,
        "random_count": 3,
        "seed": 17,
    }
    values.update(overrides)
    return values


class MutationGenerationTests(unittest.TestCase):
    def test_one_at_a_time_count_and_source_immutability(self):
        original = dict(SNAPSHOT)
        result = preview_variants(
            SNAPSHOT, ["factor_a", "factor_b"], settings(), "one-at-a-time", METRICS
        )
        self.assertEqual(result.total_count, 4)
        self.assertEqual(len(result.variants), 4)
        self.assertEqual(result.variants[0].values["factor_a"], 0.01)
        self.assertEqual(result.variants[0].values["factor_b"], 0.2)
        self.assertEqual(SNAPSHOT, original)

    def test_cartesian_count_and_order(self):
        result = preview_variants(
            SNAPSHOT, ["factor_a", "factor_b"], settings(), "cartesian", METRICS
        )
        self.assertEqual(result.total_count, 4)
        self.assertEqual(len(result.variants), 4)
        self.assertEqual(result.variants[0].values["factor_a"], 0.01)
        self.assertEqual(result.variants[0].values["factor_b"], 0.01)
        self.assertEqual(result.variants[1].values["factor_b"], 0.02)

    def test_inclusive_range(self):
        result = preview_variants(
            SNAPSHOT,
            ["factor_a"],
            settings("range", range_start=0.5, range_end=1.5, range_step=0.5),
            "one-at-a-time",
            METRICS,
        )
        self.assertEqual(result.total_count, 3)
        self.assertEqual([variant.values["factor_a"] for variant in result.variants], [0.005, 0.01, 0.015])

    def test_seeded_random_is_repeatable(self):
        first = preview_variants(
            SNAPSHOT, ["factor_a"], settings("random"), "one-at-a-time", METRICS
        )
        second = preview_variants(
            SNAPSHOT, ["factor_a"], settings("random"), "one-at-a-time", METRICS
        )
        self.assertEqual(first, second)
        self.assertEqual(first.total_count, 3)

    def test_preview_is_limited_but_count_is_complete(self):
        result = preview_variants(
            SNAPSHOT,
            ["factor_a"],
            settings(explicit_values=list(range(1, 151))),
            "one-at-a-time",
            METRICS,
            limit=10,
        )
        self.assertEqual(len(result.variants), 10)
        self.assertEqual(result.total_count, 150)

    def test_rejects_missing_ineligible_and_mixed_unit_fields(self):
        with self.assertRaises(MutationValidationError) as missing:
            preview_variants(
                SNAPSHOT, ["not_here"], settings(), "one-at-a-time", METRICS
            )
        self.assertEqual(missing.exception.issues[0]["code"], "field_missing")

        with self.assertRaises(MutationValidationError) as ineligible:
            preview_variants(
                {**SNAPSHOT, "locked": 0.2}, ["locked"], settings(), "one-at-a-time", METRICS
            )
        self.assertTrue(any(issue["code"] == "field_ineligible" for issue in ineligible.exception.issues))

        with self.assertRaises(MutationValidationError) as mixed:
            preview_variants(
                {**SNAPSHOT, "zscore": 0.4},
                ["factor_a", "zscore"],
                settings(),
                "cartesian",
                METRICS,
            )
        self.assertTrue(any(issue["code"] == "mixed_units" for issue in mixed.exception.issues))

    def test_rejects_nonpositive_range_step(self):
        with self.assertRaises(MutationValidationError):
            preview_variants(
                SNAPSHOT,
                ["factor_a"],
                settings("range", range_step=0),
                "one-at-a-time",
                METRICS,
            )


if __name__ == "__main__":
    unittest.main()
