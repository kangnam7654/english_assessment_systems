"""Regression checks for landmarks."""

import copy
import unittest

from presentation_attitude.evaluation.diagnostics import summarize
from presentation_attitude.vision.landmarks import validate_plan


class AuditTests(unittest.TestCase):
    """Exercise audit tests behavior with controlled fixtures."""
    def test_missing_frames_remain_in_denominator(self):
        """Verify missing frames remain in denominator."""
        result = summarize(
            [
                {"face_present": True, "hand_count": 2},
                {"face_present": True, "hand_count": 0},
                {"face_present": False, "hand_count": 1},
                {"face_present": False, "hand_count": 0},
            ]
        )
        self.assertEqual(result["sampled_frames"], 4)
        self.assertEqual(
            result["detected_frame_ratios"],
            {
                "face": 0.5,
                "at_least_one_hand": 0.5,
                "two_hands": 0.25,
                "face_and_at_least_one_hand": 0.25,
            },
        )

    def test_empty_decode_is_an_error_not_zero_percent(self):
        """Verify empty decode is an error not zero percent."""
        with self.assertRaises(ValueError):
            summarize([])

    def test_plan_rejects_bad_times_and_unsafe_output_ids(self):
        """Verify plan rejects bad times and unsafe output ids."""
        inventory = {"sample.mp4": {"duration_seconds": 10}}
        plan = {
            "sample_fps": 5,
            "intervals": [
                {
                    "id": "sample",
                    "file_name": "sample.mp4",
                    "start_seconds": 0,
                    "duration_seconds": 10,
                },
            ],
        }
        validate_plan(plan, inventory)
        for key, value in [
            ("start_seconds", -1),
            ("start_seconds", 1),
            ("duration_seconds", 0),
            ("duration_seconds", float("nan")),
            ("id", "../escape"),
        ]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                invalid = copy.deepcopy(plan)
                invalid["intervals"][0][key] = value
                validate_plan(invalid, inventory)

    def test_plan_rejects_duplicate_ids_and_invalid_fps(self):
        """Verify plan rejects duplicate ids and invalid fps."""
        inventory = {"sample.mp4": {"duration_seconds": 10}}
        interval = {
            "id": "sample",
            "file_name": "sample.mp4",
            "start_seconds": 0,
            "duration_seconds": 1,
        }
        with self.assertRaises(ValueError):
            validate_plan(
                {"sample_fps": 5, "intervals": [interval, interval]}, inventory
            )
        for fps in [0, -1, float("nan"), float("inf"), 1001]:
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                validate_plan({"sample_fps": fps, "intervals": [interval]}, inventory)


if __name__ == "__main__":
    unittest.main()
