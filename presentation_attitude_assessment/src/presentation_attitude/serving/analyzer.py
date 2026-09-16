"""Connect the existing feature pipeline and optional reusable GRU runtime."""

from pathlib import Path

from presentation_attitude.artifacts import sha256
from presentation_attitude.pipelines.extraction import process_video
from presentation_attitude.schema import label_mapping


class VideoAnalyzer:
    """Reuse an optional classifier across sequential worker jobs.

    Construction loads a supplied attitude-training checkpoint once and takes
    sampling/smoothing settings from it. Without a checkpoint only features
    mode is available. Each call owns a new video extraction session, so
    MediaPipe tracking never carries over between videos. Calls are designed
    for the single local worker, not concurrent use of a shared instance.
    """

    def __init__(
        self,
        settings,
        *,
        checkpoint=None,
        device="cpu",
        models_dir=None,
        model_specs=None,
    ):
        """Load an optional attitude checkpoint and establish compatible extraction settings.

        Args:
            settings: Validated configuration for this component.
            checkpoint: Path to a trusted local PyTorch checkpoint.
            device: PyTorch execution device, such as cpu, mps, or cuda.
            models_dir: Directory containing cached MediaPipe model assets.
            model_specs: Path to the MediaPipe asset specification JSON.

        Raises:
            ValueError: Serving assessment requires an attitude_training checkpoint;
                pipeline_smoke is not an attitude classifier; Unsupported attitude label
                mapping.
        """
        self.settings = settings
        self.models_dir, self.model_specs = models_dir, model_specs
        self.runtime = None
        self.checkpoint_hash = None
        self.fps, self.window = 5, 3
        if checkpoint is not None:
            from presentation_attitude.models.runtime import ClassifierRuntime

            self.runtime = ClassifierRuntime(checkpoint, device=device)
            if self.runtime.purpose != "attitude_training":
                raise ValueError(
                    "Serving assessment requires an attitude_training checkpoint; pipeline_smoke is not an attitude classifier"
                )
            if self.runtime.label_mapping != label_mapping("attitude_training"):
                raise ValueError("Unsupported attitude label mapping")
            self.checkpoint_hash = sha256(Path(checkpoint))
            self.fps = self.runtime.feature_settings["sample_fps"]
            self.window = self.runtime.feature_settings["settings"]["window"]

    def __call__(self, source, output, mode):
        """Return a JSON-ready feature/assessment result for one whole video.

        source must exist and output must be a fresh attempt directory. Extraction
        errors propagate to the worker. Missing usable features yield an unavailable
        assessment; valid features use the fixed 0.5 decision threshold. A missing
        checkpoint in assessment mode is rejected before extraction starts.

        Args:
            source: Source video path or caller-owned input stream, as required by this
                operation.
            output: Destination directory or file for generated artifacts.
            mode: Requested execution mode.

        Returns:
            JSON-ready extraction result and, when requested, an assessment or its
            unavailability reason.

        Raises:
            ValueError: No attitude-training checkpoint configured; use features mode.
        """
        if mode == "assessment" and self.runtime is None:
            raise ValueError(
                "No attitude-training checkpoint configured; use features mode"
            )
        summary = process_video(
            source,
            output,
            fps=self.fps,
            window=self.window,
            models_dir=self.models_dir,
            model_specs=self.model_specs,
            max_frames=self.settings.max_frames,
            allowed_formats="mov,matroska,avi",
            max_pixels=3840 * 2160,
        )
        result = {
            "mode": mode,
            "source_sha256": summary["source"]["sha256"],
            "features": {
                key: summary[key]
                for key in (
                    "sampled_frames",
                    "sample_fps",
                    "detected_frame_ratios",
                    "valid_frame_ratios",
                    "has_valid_features",
                    "sequence_sha256",
                )
            },
            "assessment": None,
            "notice": "Landmark detection ratios describe feature availability, not presentation attitude.",
        }
        if mode == "assessment":
            if not summary["has_valid_features"]:
                result["assessment"] = {
                    "status": "unavailable",
                    "reason": "no_valid_features",
                }
            else:
                prediction = self.runtime.predict_sequence(
                    output, max_frames=self.settings.max_frames
                )
                probability = prediction["positive_class_probability"]
                result["assessment"] = {
                    "status": "complete",
                    **prediction,
                    "label": "appropriate" if probability >= 0.5 else "inappropriate",
                    "threshold": 0.5,
                    "checkpoint_sha256": self.checkpoint_hash,
                    "notice": "Model output at a fixed threshold; deployment accuracy and probability calibration are not established.",
                }
        return result
