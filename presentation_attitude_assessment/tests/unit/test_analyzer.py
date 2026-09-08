import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from presentation_attitude.serving.settings import Settings


class AnalyzerTests(unittest.TestCase):
    def test_smoke_checkpoint_is_rejected_and_runtime_loads_once(self):
        from presentation_attitude.serving.analyzer import VideoAnalyzer

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory))
            checkpoint = Path(directory) / "weights.pt"
            checkpoint.write_bytes(b"weights")
            with patch(
                "presentation_attitude.models.runtime.ClassifierRuntime"
            ) as runtime:
                runtime.return_value.purpose = "pipeline_smoke"
                with self.assertRaisesRegex(ValueError, "pipeline_smoke"):
                    VideoAnalyzer(settings, checkpoint=checkpoint)
                runtime.reset_mock()
                runtime.return_value.purpose = "attitude_training"
                runtime.return_value.label_mapping = {
                    "0": "inappropriate",
                    "1": "appropriate",
                }
                runtime.return_value.feature_settings = {
                    "sample_fps": 5,
                    "settings": {"window": 3},
                }
                runtime.return_value.predict_sequence.return_value = {
                    "positive_class_probability": 0.7
                }
                analyzer = VideoAnalyzer(settings, checkpoint=checkpoint)
                summary = {
                    "source": {"sha256": "a"},
                    "sampled_frames": 5,
                    "sample_fps": 5,
                    "detected_frame_ratios": {},
                    "valid_frame_ratios": {},
                    "has_valid_features": True,
                    "sequence_sha256": "b",
                }
                with patch(
                    "presentation_attitude.serving.analyzer.process_video",
                    return_value=summary,
                ):
                    for _ in range(2):
                        self.assertEqual(
                            analyzer("source", "output", "assessment")["assessment"][
                                "label"
                            ],
                            "appropriate",
                        )
                    summary["has_valid_features"] = False
                    self.assertEqual(
                        analyzer("source", "output", "assessment")["assessment"][
                            "status"
                        ],
                        "unavailable",
                    )
                self.assertEqual(runtime.call_count, 1)
                self.assertEqual(runtime.return_value.predict_sequence.call_count, 2)

    def test_missing_checkpoint_fails_before_feature_extraction(self):
        from presentation_attitude.serving.analyzer import VideoAnalyzer

        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "presentation_attitude.serving.analyzer.process_video"
            ) as process:
                with self.assertRaisesRegex(
                    ValueError, "No attitude-training checkpoint"
                ):
                    VideoAnalyzer(Settings(Path(directory)))(
                        "source", "output", "assessment"
                    )
                process.assert_not_called()
