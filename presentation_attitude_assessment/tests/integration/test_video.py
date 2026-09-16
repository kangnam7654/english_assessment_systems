"""Regression checks for video."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from presentation_attitude.vision.video import FFmpegVideoReader, VideoDecodeError


class ReaderTests(unittest.TestCase):
    """Exercise reader tests behavior with controlled fixtures."""
    @classmethod
    def setUpClass(cls):
        """Create isolated fixtures and register cleanup for this test scope."""
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = cls.root / "video with spaces.mkv"
        # Lossless, asymmetric RGB frames expose channel swaps and frame reordering.
        cls.original = np.arange(20 * 24 * 32 * 3, dtype=np.uint8).reshape(
            20, 24, 32, 3
        )
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "rawvideo",
                "-pixel_format",
                "rgb24",
                "-video_size",
                "32x24",
                "-framerate",
                "10",
                "-i",
                "pipe:0",
                "-c:v",
                "ffv1",
                "-pix_fmt",
                "bgr0",
                str(cls.source),
            ],
            input=cls.original.tobytes(),
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        """Release resources created for this test scope."""
        cls.temp.cleanup()

    def test_decoded_rgb_ownership_and_clean_eof(self):
        """Verify decoded rgb ownership and clean eof."""
        with FFmpegVideoReader(self.source, fps=10) as reader:
            frames = list(reader)
        np.testing.assert_array_equal(frames, self.original)
        self.assertEqual(frames[0].shape, (24, 32, 3))
        self.assertEqual(frames[0].dtype, np.uint8)
        self.assertTrue(frames[0].flags.c_contiguous)
        self.assertFalse(frames[0].flags.writeable)
        self.assertEqual(reader.process.returncode, 0)
        self.assertTrue(reader.process.stdout.closed)
        self.assertFalse(reader._stderr_thread.is_alive())
        with self.assertRaises(StopIteration):
            next(reader)

    def test_seek_and_sampling_match_previous_png_pipeline(self):
        """Verify seek and sampling match previous png pipeline."""
        destination = self.root / "png-reference"
        destination.mkdir()
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-nostdin",
                "-ss",
                "0.3",
                "-i",
                str(self.source),
                "-t",
                "1.2",
                "-map",
                "0:v:0",
                "-vf",
                "fps=fps=5:start_time=0",
                "-fps_mode",
                "passthrough",
                str(destination / "%06d.png"),
            ],
            check=True,
        )
        reference = [
            cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
            for p in sorted(destination.glob("*.png"))
        ]
        with FFmpegVideoReader(
            self.source, fps=5, start_seconds=0.3, duration_seconds=1.2
        ) as reader:
            actual = list(reader)
        self.assertEqual(len(actual), 6)
        np.testing.assert_array_equal(actual, reference)

    def test_context_reaps_process_on_break_and_consumer_exception(self):
        """Verify context reaps process on break and consumer exception."""
        for fail in (False, True):
            with self.subTest(fail=fail):
                try:
                    with FFmpegVideoReader(self.source) as reader:
                        for frame in reader:
                            if fail:
                                raise LookupError("consumer failed")
                            break
                except LookupError:
                    pass
                self.assertIsNotNone(reader.process.poll())
                self.assertTrue(reader.process.stdout.closed)
                self.assertTrue(reader.process.stderr.closed)
                self.assertFalse(reader._stderr_thread.is_alive())
                reader.close()

    def test_empty_interval_is_error(self):
        """Verify empty interval is error."""
        with self.assertRaisesRegex(VideoDecodeError, "no sampled frames"):
            with FFmpegVideoReader(self.source, start_seconds=100) as reader:
                list(reader)
        self.assertIsNotNone(reader.process.poll())

    def test_rotation_metadata_keeps_upright_shape_and_pixels(self):
        """Verify rotation metadata keeps upright shape and pixels."""
        unrotated, rotated = self.root / "base.mp4", self.root / "rotated.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(self.source),
                "-c:v",
                "libx264rgb",
                "-crf",
                "0",
                str(unrotated),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-display_rotation",
                "90",
                "-i",
                str(unrotated),
                "-c",
                "copy",
                str(rotated),
            ],
            check=True,
        )
        with FFmpegVideoReader(rotated, fps=10) as reader:
            frames = list(reader)
        self.assertEqual((reader.width, reader.height), (24, 32))
        np.testing.assert_array_equal(frames, np.rot90(self.original, axes=(1, 2)))

    def test_decoder_error_drains_large_stderr_without_deadlock(self):
        """Verify decoder error drains large stderr without deadlock."""
        real_popen = subprocess.Popen

        def failing_decoder(command, **kwargs):
            """Start a fake decoder process that exercises the error path.

            Args:
                command: Subprocess command being replaced by the test decoder.
                **kwargs: Keyword arguments forwarded to the operation under test.

            Returns:
                Fake decoder subprocess used to exercise stderr and failure handling.
            """
            return real_popen(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('x'*200000); sys.exit(9)",
                ],
                **kwargs,
            )

        # Probe stays real; only replace the subsequent FFmpeg Popen launch.
        with patch("presentation_attitude.vision.video.subprocess.Popen") as fake:
            # subprocess.run also uses Popen, so let the ffprobe command through.
            fake.side_effect = lambda command, **kw: (
                real_popen(command, **kw)
                if command[0] == "ffprobe"
                else failing_decoder(command, **kw)
            )
            with self.assertRaisesRegex(VideoDecodeError, "exited with 9"):
                with FFmpegVideoReader(self.source) as reader:
                    list(reader)
        self.assertFalse(reader._stderr_thread.is_alive())
        self.assertLessEqual(sum(map(len, reader._stderr)), 65536)

    def test_invalid_input_and_context_usage(self):
        """Verify invalid input and context usage."""
        with self.assertRaises(FileNotFoundError):
            FFmpegVideoReader(self.root / "missing.mp4")
        bad = self.root / "broken.mp4"
        bad.write_bytes(b"not a video")
        with self.assertRaisesRegex(VideoDecodeError, "ffprobe failed"):
            with FFmpegVideoReader(bad):
                pass
        for options in (
            {"fps": 0},
            {"fps": float("nan")},
            {"start_seconds": -1},
            {"duration_seconds": 0},
        ):
            with self.assertRaises(ValueError):
                FFmpegVideoReader(self.source, **options)
        with self.assertRaisesRegex(RuntimeError, "with block"):
            next(FFmpegVideoReader(self.source))


if __name__ == "__main__":
    unittest.main()
