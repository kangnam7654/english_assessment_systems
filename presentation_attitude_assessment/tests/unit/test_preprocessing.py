"""Regression checks for preprocessing."""

import copy
import unittest

import numpy as np

from presentation_attitude.data.preprocessing import preprocess, restore_xy


def frame(index=0, *, face=True, hands=True):
    """Construct one synthetic landmark frame with optional face and hands.

    Args:
        index: Zero-based item or frame index.
        face: Whether to include a synthetic face detection.
        hands: Detected hand records with handedness confidence.

    Returns:
        Synthetic frame record with presence and landmark metadata.
    """
    angle = np.linspace(0, 2 * np.pi, 478, endpoint=False)
    points = np.column_stack(
        (0.5 + 0.1 * np.cos(angle), 0.3 + 0.15 * np.sin(angle), angle * 0)
    )

    def hand(x):
        """Build a synthetic hand detection at the requested horizontal position.

        Args:
            x: Horizontal position of the synthetic hand landmarks.

        Returns:
            Synthetic hand record at the requested horizontal position.
        """
        return [[x + i * 0.001, 0.7 + i * 0.001, i * -0.001] for i in range(21)]

    detections = (
        [
            {"landmarks": hand(x), "handedness": side, "handedness_score": 0.99}
            for side, x in (("Left", 0.25), ("Right", 0.75))
        ]
        if hands
        else []
    )
    return {
        "frame_index": index,
        "interval_timestamp_ms": index * 200,
        "source_grid_seconds": index / 5,
        "face_present": face,
        "face_landmarks": points.tolist() if face else [],
        "hand_count": len(detections),
        "hands": detections,
    }


class PreprocessTests(unittest.TestCase):
    """Exercise preprocess tests behavior with controlled fixtures."""
    def test_translation_and_uniform_scale_invariance_and_inverse(self):
        """Verify translation and uniform scale invariance and inverse."""
        source = frame()
        transformed = copy.deepcopy(source)
        size = np.array([640, 360])
        for pts in [transformed["face_landmarks"]] + [
            h["landmarks"] for h in transformed["hands"]
        ]:
            for point in pts:
                point[:2] = (
                    (np.array(point[:2]) * size * 1.4 + [21, -13]) / size
                ).tolist()
        a, b = [preprocess([r], *size, 5)[0] for r in (source, transformed)]
        for part in a["valid"]:
            np.testing.assert_allclose(
                a["normalized_xy"][part], b["normalized_xy"][part], atol=1e-12
            )
        np.testing.assert_allclose(
            restore_xy(a["normalized_xy"]["face"], size, a["anchor"]),
            np.asarray(source["face_landmarks"])[:, :2],
            atol=1e-12,
        )
        self.assertNotEqual(a["anchor"]["center_px"], b["anchor"]["center_px"])

    def test_pixel_aspect_ratio_and_resolution(self):
        """Verify pixel aspect ratio and resolution."""
        source = frame()
        original = preprocess([source], 640, 360, 5)[0]
        larger = preprocess([source], 1280, 720, 5)[0]
        for part in original["valid"]:
            np.testing.assert_allclose(
                original["normalized_xy"][part], larger["normalized_xy"][part]
            )
        square = copy.deepcopy(source)
        for pts in [square["face_landmarks"]] + [
            h["landmarks"] for h in square["hands"]
        ]:
            for point in pts:
                point[1] *= 360 / 640
        result = preprocess([square], 640, 640, 5)[0]
        np.testing.assert_allclose(
            original["normalized_xy"]["Left"], result["normalized_xy"]["Left"]
        )

    def test_raw_preserved_and_missing_anchor_does_not_erase_hands(self):
        """Verify raw preserved and missing anchor does not erase hands."""
        rows = [frame(0), frame(1, face=False), frame(2)]
        before = copy.deepcopy(rows)
        result = preprocess(rows, 640, 360, 5)
        self.assertEqual(rows, before)
        self.assertEqual([r["raw"] for r in result], before)
        self.assertEqual(result[1]["raw"]["hand_count"], 2)
        self.assertIsNone(result[1]["smoothed_xy"]["Left"])
        self.assertEqual(result[1]["missing_reason"]["Left"], "face_anchor_unavailable")
        self.assertEqual(result[0]["smoothing_support"]["face"], 1)
        self.assertEqual(result[2]["smoothing_support"]["face"], 1)
        self.assertNotEqual(
            result[0]["segment_id"]["face"], result[2]["segment_id"]["face"]
        )

    def test_centered_mean_and_linear_motion(self):
        """Verify centered mean and linear motion."""
        rows = [frame(i) for i in range(5)]
        for i, row in enumerate(rows):
            for point in row["hands"][0]["landmarks"]:
                point[0] += i * 0.01
        result = preprocess(rows, 640, 360, 5)
        np.testing.assert_allclose(
            result[2]["smoothed_xy"]["Left"], result[2]["normalized_xy"]["Left"]
        )
        self.assertEqual(result[2]["smoothing_support"]["Left"], 3)
        expected = result[0]["normalized_xy"]["Left"]
        np.testing.assert_allclose(result[0]["smoothed_xy"]["Left"], expected)
        self.assertEqual(result[-1]["smoothing_support"]["Left"], 1)

    def test_short_segment_keeps_motion(self):
        """Verify short segment keeps motion."""
        rows = [frame(0), frame(1)]
        rows[1]["hands"][0]["landmarks"][8][0] += 0.06
        result = preprocess(rows, 640, 360, 5)
        for row in result:
            np.testing.assert_allclose(
                row["smoothed_xy"]["Left"], row["normalized_xy"]["Left"]
            )
            self.assertEqual(row["smoothing_support"]["Left"], 1)
        self.assertNotEqual(
            result[0]["smoothed_xy"]["Left"][8], result[1]["smoothed_xy"]["Left"][8]
        )

    def test_impulse_is_reduced_without_filling_missing_hand(self):
        """Verify impulse is reduced without filling missing hand."""
        rows = [frame(i) for i in range(5)]
        rows[2]["hands"][0]["landmarks"][8][0] += 0.06
        result = preprocess(rows, 640, 360, 5)
        base = result[0]["normalized_xy"]["Left"][8][0]
        raw_delta = result[2]["normalized_xy"]["Left"][8][0] - base
        self.assertAlmostEqual(
            result[2]["smoothed_xy"]["Left"][8][0] - base, raw_delta / 3
        )
        rows[2] = frame(2, hands=False)
        result = preprocess(rows, 640, 360, 5)
        self.assertIsNone(result[2]["smoothed_xy"]["Left"])
        self.assertNotEqual(
            result[1]["segment_id"]["Left"], result[3]["segment_id"]["Left"]
        )

    def test_reordered_detections_are_not_swapped_slots(self):
        """Verify reordered detections are not swapped slots."""
        rows = [frame(0), frame(1)]
        rows[1]["hands"].reverse()
        result = preprocess(rows, 640, 360, 5)
        self.assertEqual(result[1]["hand_source_index"]["Left"], 1)
        self.assertEqual(result[1]["hand_switch_suspected"], [])
        np.testing.assert_allclose(
            result[0]["normalized_xy"]["Left"], result[1]["normalized_xy"]["Left"]
        )

    def test_swapped_labels_low_confidence_and_duplicate_labels(self):
        """Verify swapped labels low confidence and duplicate labels."""
        rows = [frame(0), frame(1)]
        for hand in rows[1]["hands"]:
            hand["handedness"] = "Right" if hand["handedness"] == "Left" else "Left"
        result = preprocess(rows, 640, 360, 5)
        self.assertEqual(result[1]["hand_switch_suspected"], ["Left", "Right"])
        self.assertFalse(result[1]["valid"]["Left"])
        duplicate = frame()
        duplicate["hands"][1]["handedness"] = "Left"
        result = preprocess([duplicate], 640, 360, 5)[0]
        self.assertEqual(result["missing_reason"]["Left"], "duplicate_handedness")
        low = frame()
        low["hands"][0]["handedness_score"] = 0.6
        self.assertEqual(
            preprocess([low], 640, 360, 5)[0]["missing_reason"]["Left"],
            "low_handedness_score",
        )

    def test_time_gap_explicit_cut_and_anchor_jump_reset_smoothing(self):
        """Verify time gap explicit cut and anchor jump reset smoothing."""
        for mode in ("gap", "cut", "jump"):
            with self.subTest(mode=mode):
                rows = [frame(0), frame(1)]
                if mode == "gap":
                    rows[1]["interval_timestamp_ms"] = 1000
                elif mode == "cut":
                    rows[1]["break_before"] = True
                else:
                    for point in rows[1]["face_landmarks"]:
                        point[0] += 0.5
                result = preprocess(rows, 640, 360, 5)
                self.assertEqual(result[0]["smoothing_support"]["face"], 1)
                self.assertEqual(result[1]["smoothing_support"]["face"], 1)

    def test_degenerate_face_and_invalid_inputs(self):
        """Verify degenerate face and invalid inputs."""
        degenerate = frame()
        degenerate["face_landmarks"] = [[0.5, 0.5, 0]] * 478
        result = preprocess([degenerate], 640, 360, 5)[0]
        self.assertEqual(result["missing_reason"]["face"], "degenerate_face_scale")
        for rows in ([], [frame(1), frame(0)], [frame(0), frame(0)]):
            with self.assertRaises(ValueError):
                preprocess(rows, 640, 360, 5)
        malformed = frame()
        malformed["hands"][0]["landmarks"][0][2] = float("nan")
        with self.assertRaises(ValueError):
            preprocess([malformed], 640, 360, 5)
        with self.assertRaises(ValueError):
            preprocess([frame()], 640, 360, 5, config={"window": 2})


if __name__ == "__main__":
    unittest.main()
