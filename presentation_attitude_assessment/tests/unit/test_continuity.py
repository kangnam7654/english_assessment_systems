"""Regression checks for continuity."""

import unittest

from presentation_attitude.evaluation.diagnostics import runs


class ContinuityTests(unittest.TestCase):
    """Exercise continuity tests behavior with controlled fixtures."""
    def test_absence_breaks_runs_and_stays_in_denominator(self):
        """Verify absence breaks runs and stays in denominator."""
        result = runs([True, True, False, False, False, True], 5)
        self.assertEqual(result["present_ratio"], 0.5)
        self.assertEqual(result["longest_present_frames"], 2)
        self.assertEqual(result["longest_missing_frames"], 3)
        self.assertEqual(result["runs"][0]["sampled_coverage_seconds"], 0.4)
        self.assertEqual(result["runs"][0]["first_to_last_sample_seconds"], 0.2)

    def test_anchor_break_splits_otherwise_present_features(self):
        """Verify anchor break splits otherwise present features."""
        result = runs([True, True, True], 5, [0, 0, 1])
        self.assertEqual(result["longest_present_frames"], 2)

    def test_all_present_all_missing_and_single_sample(self):
        """Verify all present all missing and single sample."""
        self.assertEqual(runs([False, False], 5)["longest_present_frames"], 0)
        result = runs([True], 5)
        self.assertEqual(result["longest_missing_frames"], 0)
        self.assertEqual(result["runs"][0]["first_to_last_sample_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
