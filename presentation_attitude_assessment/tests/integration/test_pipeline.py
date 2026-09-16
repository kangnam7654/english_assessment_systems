"""Regression checks for pipeline."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from presentation_attitude.artifacts import iter_sequence
from presentation_attitude.pipelines.extraction import process_video
from presentation_attitude.vision.video import FFmpegVideoReader


class MissingDetector:
    """No-download stub: video IO and preprocessing remain real."""

    def __init__(self, model_dir):
        """Initialize the controlled test double and its recorded responses.

        Args:
            model_dir: Directory containing cached MediaPipe model assets.
        """
        self.closed = False

    def __enter__(self):
        """Enter the test double's resource context.

        Returns:
            This initialized context-managed resource.
        """
        return self

    def __exit__(self, *exc):
        """Leave the test double's resource context.

        Args:
            *exc: Exception details supplied by the context manager protocol.
        """
        self.closed = True

    def detect(self, rgb, index, timestamp_ms, source_seconds):
        """Return deterministic missing-landmark observations for the input frame.

        Args:
            rgb: RGB uint8 frame of shape (H, W, 3).
            index: Zero-based item or frame index.
            timestamp_ms: Strictly increasing MediaPipe timestamp in milliseconds.
            source_seconds: Time on the sampling grid, not an exact source PTS.

        Returns:
            Synthetic raw landmark observation for the requested frame.
        """
        return {
            "frame_index": index,
            "interval_timestamp_ms": timestamp_ms,
            "source_grid_seconds": source_seconds,
            "face_present": False,
            "face_landmarks": [],
            "hand_count": 0,
            "hands": [],
        }


class WholeVideoTests(unittest.TestCase):
    """Exercise whole video tests behavior with controlled fixtures."""
    def setUp(self):
        """Create isolated fixtures and register cleanup for this test scope."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.video = self.root / "whole video.mkv"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=size=32x24:rate=10:duration=2",
                "-c:v",
                "ffv1",
                str(self.video),
            ],
            check=True,
        )
        self.specs = self.root / "models.json"
        self.specs.write_text("{}")

    def run_video(self, output, **kwargs):
        """Process the fixture video into the supplied output directory.

        Args:
            output: Destination directory or file for generated artifacts.
            **kwargs: Keyword arguments forwarded to the operation under test.

        Returns:
            Extraction summary produced by the fixture pipeline.
        """
        return process_video(
            self.video,
            output,
            model_specs=self.specs,
            models_dir=self.root / "models",
            **kwargs,
        )

    def test_whole_video_retains_missing_frames_and_reads_sequence(self):
        """Verify whole video retains missing frames and reads sequence."""
        output = self.root / "output"
        detector = MissingDetector(None)
        with patch(
            "presentation_attitude.pipelines.extraction.LandmarkExtractor",
            return_value=detector,
        ):
            result = self.run_video(output)
        records = list(iter_sequence(output))
        self.assertTrue(detector.closed)
        self.assertEqual(len(records), 10)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["has_valid_features"])
        self.assertEqual(
            result["valid_frame_counts"], {"face": 0, "Left": 0, "Right": 0}
        )
        self.assertEqual(
            [r["raw"]["interval_timestamp_ms"] for r in records],
            list(range(0, 2000, 200)),
        )
        self.assertNotIn("-t", result["ffmpeg_command"])
        self.assertEqual(
            set(p.name for p in output.iterdir()), {"sequence.jsonl", "summary.json"}
        )
        with (output / "sequence.jsonl").open("a") as stream:
            stream.write("{}\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            list(iter_sequence(output))

    def test_detector_failure_closes_reader_and_rejects_partial_output(self):
        """Verify detector failure closes reader and rejects partial output."""
        output = self.root / "failed"
        detector = MissingDetector(None)
        detect = detector.detect

        def fail(rgb, index, timestamp_ms, source_seconds):
            """Raise the simulated detector failure used to verify cleanup.

            Args:
                rgb: RGB uint8 frame of shape (H, W, 3).
                index: Zero-based item or frame index.
                timestamp_ms: Strictly increasing MediaPipe timestamp in milliseconds.
                source_seconds: Time on the sampling grid, not an exact source PTS.

            Returns:
                Detector output before the configured failure point is reached.
            """
            if index == 4:
                raise RuntimeError("inference failed")
            return detect(rgb, index, timestamp_ms, source_seconds)

        detector.detect = fail
        reader = FFmpegVideoReader(self.video)
        with (
            patch(
                "presentation_attitude.pipelines.extraction.LandmarkExtractor",
                return_value=detector,
            ),
            patch(
                "presentation_attitude.pipelines.extraction.FFmpegVideoReader",
                return_value=reader,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "inference failed"):
                self.run_video(output)
        self.assertTrue(detector.closed)
        self.assertIsNotNone(reader.process.poll())
        self.assertTrue(reader.process.stdout.closed)
        self.assertEqual(
            json.loads((output / "summary.json").read_text())["status"], "failed"
        )
        self.assertFalse((output / "sequence.jsonl").exists())
        self.assertTrue((output / "sequence.jsonl.partial").exists())
        with self.assertRaisesRegex(ValueError, "completed"):
            list(iter_sequence(output))

    def test_invalid_arguments_and_existing_output_do_not_overwrite(self):
        """Verify invalid arguments and existing output do not overwrite."""
        output = self.root / "invalid"
        for kwargs in ({"window": 2}, {"fps": 0}):
            with self.assertRaises(ValueError):
                self.run_video(output, **kwargs)
            self.assertFalse(output.exists())
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("keep")
        with self.assertRaises(FileExistsError):
            self.run_video(output)
        self.assertEqual(marker.read_text(), "keep")

    def test_serving_frame_limit_fails_without_partial_success(self):
        """Verify serving frame limit fails without partial success."""
        detector = MissingDetector(None)
        output = self.root / "limited"
        with patch(
            "presentation_attitude.pipelines.extraction.LandmarkExtractor",
            return_value=detector,
        ):
            with self.assertRaisesRegex(ValueError, "sampled frame limit"):
                self.run_video(output, max_frames=9)
        self.assertTrue(detector.closed)
        self.assertFalse((output / "sequence.jsonl").exists())
        with patch(
            "presentation_attitude.pipelines.extraction.LandmarkExtractor",
            return_value=MissingDetector(None),
        ):
            result = self.run_video(self.root / "exact", max_frames=10)
        self.assertEqual(result["sampled_frames"], 10)

    def test_serving_decoder_limits(self):
        """Verify serving decoder limits."""
        with FFmpegVideoReader(
            self.video, allowed_formats="mov,matroska,avi"
        ) as reader:
            self.assertEqual(len(list(reader)), 10)
        with self.assertRaisesRegex(RuntimeError, "pixel limit"):
            with FFmpegVideoReader(self.video, max_pixels=10):
                pass
        playlist = self.root / "playlist.mp4"
        playlist.write_text(
            "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nhttp://127.0.0.1:1/no-video.ts\n#EXT-X-ENDLIST\n"
        )
        with self.assertRaisesRegex(RuntimeError, "ffprobe failed"):
            with FFmpegVideoReader(playlist, allowed_formats="mov,matroska,avi"):
                pass
