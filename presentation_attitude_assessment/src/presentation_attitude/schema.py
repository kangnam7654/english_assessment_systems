"""Shared landmark layout, feature contract and classification labels; independent of ML runtimes."""

PART_COUNTS = {"face": 478, "Left": 21, "Right": 21}
PARTS = tuple(PART_COUNTS)
MASK_SIZE = len(PARTS)
INPUT_SIZE = sum(PART_COUNTS.values()) * 2 + len(PART_COUNTS)
FEATURE_SCHEMA = "smoothed_xy_face_left_right_1040_plus_valid_3_v1"


def feature_settings(summary):
    """Keep extraction settings identical across splits and checkpoint inference.

    Args:
        summary: Completed extraction summary containing settings and provenance.

    Returns:
        Canonical settings required to match extraction and checkpoint inputs.
    """
    return {
        key: summary[key]
        for key in (
            "sample_fps",
            "settings",
            "models",
            "z_policy",
            "part_order",
            "landmark_counts",
        )
    }


def label_mapping(purpose: str) -> dict[str, str]:
    """Keep synthetic test labels distinct from presentation-attitude labels.

    Args:
        purpose: Dataset or checkpoint purpose used to select the label contract.

    Returns:
        Class-ID to label mapping appropriate to the checkpoint purpose.

    Raises:
        ValueError: The purpose is not a supported training or synthetic-smoke purpose.
    """
    if purpose == "pipeline_smoke":
        return {"0": "test_pattern_a", "1": "test_pattern_b"}
    if purpose == "attitude_training":
        return {"0": "inappropriate", "1": "appropriate"}
    raise ValueError(f"Unsupported classification purpose: {purpose}")
