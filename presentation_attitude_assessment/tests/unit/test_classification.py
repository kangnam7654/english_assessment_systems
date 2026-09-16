"""Regression checks for classification."""

import math
import unittest

from presentation_attitude.evaluation.classification import binary_metrics


class ClassificationTests(unittest.TestCase):
    """Exercise classification tests behavior with controlled fixtures."""
    def test_roc_auc_ranking_and_ties(self):
        """Verify roc auc ranking and ties."""
        for labels, probabilities, expected in [
            ([0, 1], [0.1, 0.9], 1.0),
            ([0, 1], [0.9, 0.1], 0.0),
            ([0, 0, 1, 1], [0.5, 0.5, 0.5, 0.5], 0.5),
            ([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8], 0.75),
            ([0, 1, 0, 1], [0.1, 0.5, 0.5, 0.9], 0.875),
        ]:
            with self.subTest(probabilities=probabilities):
                self.assertEqual(
                    binary_metrics(labels, probabilities)["roc_auc"], expected
                )
                self.assertEqual(
                    binary_metrics(labels[::-1], probabilities[::-1], threshold=1)[
                        "roc_auc"
                    ],
                    expected,
                )

    def test_roc_auc_requires_both_classes(self):
        """Verify roc auc requires both classes."""
        for labels in ([0, 0], [1, 1]):
            self.assertIsNone(binary_metrics(labels, [0.1, 0.9])["roc_auc"])

    def test_hand_calculated_confusion_and_class_metrics(self):
        """Verify hand calculated confusion and class metrics."""
        result = binary_metrics([0, 0, 1, 1, 1], [0.1, 0.8, 0.2, 0.5, 0.9])
        self.assertEqual(result["confusion_matrix"]["values"], [[1, 1], [1, 2]])
        self.assertEqual(result["accuracy"], 3 / 5)
        self.assertEqual(result["precision"], 2 / 3)
        self.assertEqual(result["recall"], 2 / 3)
        self.assertEqual(result["f1"], 2 / 3)
        self.assertAlmostEqual(result["macro_f1"], 7 / 12)
        self.assertEqual(result["per_class"]["0"]["support"], 2)

    def test_undefined_is_null_and_complete_misses_are_zero(self):
        """Verify undefined is null and complete misses are zero."""
        result = binary_metrics([0, 0], [0.1, 0.2])
        for key in ("precision", "recall", "f1", "macro_f1"):
            self.assertIsNone(result[key])
        result = binary_metrics([0, 1], [0.1, 0.2])
        self.assertIsNone(result["precision"])
        self.assertEqual(result["recall"], 0)
        self.assertEqual(result["f1"], 0)

    def test_threshold_and_invalid_inputs(self):
        """Verify threshold and invalid inputs."""
        self.assertEqual(binary_metrics([1], [0.5])["accuracy"], 1)
        self.assertEqual(binary_metrics([1], [0.5], threshold=0.6)["accuracy"], 0)
        for labels, probabilities in [
            ([], []),
            ([1], []),
            ([True], [0.1]),
            ([2], [0.1]),
            ([1], [math.nan]),
            ([0], [1.1]),
        ]:
            with (
                self.subTest(labels=labels, probabilities=probabilities),
                self.assertRaises(ValueError),
            ):
                binary_metrics(labels, probabilities)
        with self.assertRaises(ValueError):
            binary_metrics([0], [0.1], threshold=math.inf)
