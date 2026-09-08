import unittest

import numpy as np

from presentation_attitude.data.preprocessing import iter_preprocess


def rows(count):
    for index in range(count):
        points = np.zeros((478, 3))
        points[0, :2], points[1, :2] = (0.2, 0.2), (0.8, 0.8)
        points[2:, :2] = (0.4 + (index % 3) * 0.05, 0.5)
        yield {
            "frame_index": index,
            "interval_timestamp_ms": index * 200,
            "source_grid_seconds": index / 5,
            "face_present": True,
            "face_landmarks": points.tolist(),
            "hand_count": 0,
            "hands": [],
        }


class StreamingTests(unittest.TestCase):
    def test_centered_window_and_missing_segment_boundaries(self):
        raw = list(rows(13))
        raw[6].update(face_present=False, face_landmarks=[])
        actual = list(iter_preprocess(iter(raw), 640, 360, 5, config={"window": 5}))
        self.assertEqual([r["raw"] for r in actual], raw)
        for i, record in enumerate(actual):
            if i == 6:
                self.assertFalse(record["valid"]["face"])
                self.assertIsNone(record["smoothed_xy"]["face"])
                continue
            indices = range(i - 2, i + 3) if i in (2, 3, 9, 10) else [i]
            expected = np.mean(
                [actual[j]["normalized_xy"]["face"] for j in indices], axis=0
            )
            np.testing.assert_array_equal(record["smoothed_xy"]["face"], expected)
            self.assertEqual(record["smoothing_support"]["face"], len(indices))

    def test_consumes_only_required_future_frames(self):
        consumed = 0

        def source():
            nonlocal consumed
            for row in rows(1000):
                consumed += 1
                yield row

        iterator = iter_preprocess(source(), 640, 360, 5, config={"window": 5})
        for index in range(1000):
            self.assertEqual(next(iterator)["raw"]["frame_index"], index)
            self.assertEqual(consumed, min(1000, index + 3))
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_short_video_flushes_every_frame_without_partial_average(self):
        actual = list(iter_preprocess(rows(2), 640, 360, 5, config={"window": 7}))
        self.assertEqual(len(actual), 2)
        for record in actual:
            self.assertEqual(
                record["smoothed_xy"]["face"], record["normalized_xy"]["face"]
            )
            self.assertEqual(record["smoothing_support"]["face"], 1)

    def test_invalid_window_and_empty_iterator(self):
        for window in (0, 2, -1, True):
            with self.subTest(window=window), self.assertRaises(ValueError):
                list(iter_preprocess(rows(1), 640, 360, 5, config={"window": window}))
        with self.assertRaisesRegex(ValueError, "Empty"):
            list(iter_preprocess(iter(()), 640, 360, 5))
