import io
import unittest

from presentation_attitude.vision.video import VideoDecodeError, read_frame_bytes


class ShortReads(io.BytesIO):
    def read(self, size):
        return super().read(min(size, 7))


class FrameBytesTests(unittest.TestCase):
    def test_short_reads_and_truncated_frame(self):
        self.assertEqual(read_frame_bytes(ShortReads(b"a" * 53), 53), b"a" * 53)
        self.assertIsNone(read_frame_bytes(io.BytesIO(), 53))
        with self.assertRaisesRegex(VideoDecodeError, "Truncated"):
            read_frame_bytes(ShortReads(b"a" * 52), 53)
