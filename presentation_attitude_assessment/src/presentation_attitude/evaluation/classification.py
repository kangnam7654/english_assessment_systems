"""Binary classification metrics, independent of Torch and detector runtimes."""

import math
from itertools import groupby


def _roc_auc(labels, probabilities):
    """Rank positive/negative pairs; equal scores contribute half a win.

    Args:
        labels: Ground-truth binary labels in the same order as predictions.
        probabilities: Positive-class probabilities in [0, 1].

    Returns:
        Pairwise ROC-AUC, or None when one class is absent.
    """
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return None
    negative_count = 0
    wins = 0.0
    for _, group in groupby(sorted(zip(probabilities, labels)), key=lambda row: row[0]):
        group_labels = [label for _, label in group]
        group_positives = sum(group_labels)
        group_negatives = len(group_labels) - group_positives
        wins += group_positives * (negative_count + group_negatives / 2)
        negative_count += group_negatives
    return wins / (positives * negatives)


def binary_metrics(labels, probabilities, *, threshold=0.5):
    """Compute binary metrics from equally sized, nonempty sequences.

    labels are integer 0/1; probabilities are finite values in [0, 1].
    A score >= threshold predicts class 1. Confusion-matrix rows are true
    labels and columns predictions, both ordered [0, 1]. Zero-denominator
    metrics return None; ROC-AUC is None unless both classes occur and gives
    half credit for ties. Invalid inputs raise ValueError.

    Args:
        labels: Ground-truth binary labels in the same order as predictions.
        probabilities: Positive-class probabilities in [0, 1].
        threshold: Decision or confidence threshold.

    Returns:
        Confusion matrix and binary metrics; undefined metrics are None.

    Raises:
        ValueError: Threshold must be finite and in [0, 1]; Nonempty, equally sized
            labels and probabilities required; Labels must be binary integers;
            Probabilities must be finite and in [0, 1].
    """
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("Threshold must be finite and in [0, 1]")
    if not labels or len(labels) != len(probabilities):
        raise ValueError("Nonempty, equally sized labels and probabilities required")
    matrix = [[0, 0], [0, 0]]
    for label, probability in zip(labels, probabilities):
        if type(label) is not int or label not in (0, 1):
            raise ValueError("Labels must be binary integers")
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Probabilities must be finite and in [0, 1]")
        matrix[label][int(probability >= threshold)] += 1

    def ratio(numerator, denominator):
        """Return a ratio, or None when its denominator is zero.

        Args:
            numerator: Numerator of the reported ratio.
            denominator: Denominator; zero indicates an undefined ratio.

        Returns:
            Quotient, or None when the denominator is zero.
        """
        return numerator / denominator if denominator else None

    per_class = {}
    for label in (0, 1):
        tp = matrix[label][label]
        fp, fn = matrix[1 - label][label], matrix[label][1 - label]
        per_class[str(label)] = {
            "support": sum(matrix[label]),
            "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, tp + fn),
            "f1": ratio(2 * tp, 2 * tp + fp + fn),
        }
    f1s = [item["f1"] for item in per_class.values()]
    return {
        "samples": len(labels),
        "threshold": threshold,
        "accuracy": (matrix[0][0] + matrix[1][1]) / len(labels),
        "precision": per_class["1"]["precision"],
        "recall": per_class["1"]["recall"],
        "f1": per_class["1"]["f1"],
        "macro_f1": sum(f1s) / 2 if all(v is not None for v in f1s) else None,
        "roc_auc": _roc_auc(labels, probabilities),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": [0, 1],
            "rows": "true",
            "columns": "predicted",
            "values": matrix,
        },
        "undefined_metric_policy": "null when denominator is zero; macro_f1 null if a class F1 is undefined; roc_auc null unless both classes are present",
    }
