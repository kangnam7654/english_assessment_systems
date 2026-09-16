"""Regression checks for video."""

import io
import unittest

from presentation_attitude.vision.video import VideoDecodeError, read_frame_bytes


class ShortReads(io.BytesIO):
    """Exercise short reads behavior with controlled fixtures."""
    def read(self, size):
        """Simulate the stream read behavior required by this test.

        Args:
            size: Maximum bytes requested by the simulated reader.

        Returns:
            Bytes supplied by the controlled test stream.
        """
        return super().read(min(size, 7))


class FrameBytesTests(unittest.TestCase):
    """Exercise frame bytes tests behavior with controlled fixtures."""
    def test_short_reads_and_truncated_frame(self):
        """Verify short reads and truncated frame."""
        self.assertEqual(read_frame_bytes(ShortReads(b"a" * 53), 53), b"a" * 53)
        self.assertIsNone(read_frame_bytes(io.BytesIO(), 53))
        with self.assertRaisesRegex(VideoDecodeError, "Truncated"):
            read_frame_bytes(ShortReads(b"a" * 52), 53)
