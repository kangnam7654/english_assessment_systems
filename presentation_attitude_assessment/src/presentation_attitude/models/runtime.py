"""Reusable checkpoint runtime for video-level classification."""

import torch

from presentation_attitude.data.dataset import load_features
from presentation_attitude.models.gru import GRUClassifier
from presentation_attitude.schema import FEATURE_SCHEMA, feature_settings


class ClassifierRuntime:
    """Load a trusted local checkpoint once for repeated inference.

    Owns an eval-mode network on the selected device. Use predict_sequence()
    for stored features or predict_logits() for validated batches; callers do
    not change the internal model's training state or weights. Metadata exposes
    the checkpoint purpose, labels, feature settings and training provenance.
    A runtime contains no cross-video recurrent state.
    """

    def __init__(self, checkpoint, *, device="cpu"):
        self.device = torch.device(device)
        state = torch.load(checkpoint, map_location=self.device, weights_only=True)
        if state["feature_schema"] != FEATURE_SCHEMA:
            raise ValueError("Unsupported checkpoint feature schema")
        self._model = GRUClassifier(**state["model_config"]).to(self.device)
        self._model.load_state_dict(state["model_state_dict"])
        self._model.eval()
        self.purpose = state["purpose"]
        self.label_mapping = state["label_mapping"]
        self.feature_settings = state["feature_settings"]
        self.training_manifest_sha256 = state.get("manifest_sha256")
        self.training_sample_provenance = state.get("training_sample_provenance")

    @torch.inference_mode()
    def predict_logits(
        self, features: torch.Tensor, lengths: torch.Tensor
    ) -> torch.Tensor:
        """Infer one uncalibrated logit per video from an already validated batch.

        Args:
            features: Float32 tensor (B, T, INPUT_SIZE), right-padded with zeros.
            lengths: Int64 tensor (B,) of positive, unpadded sequence lengths.

        Returns:
            Tensor (B,) on this runtime's device, with gradients disabled.
            Each video starts with a fresh GRU hidden state.

        Callers supplying tensors must enforce the checkpoint's feature settings.
        Use predict_sequence() for validation of a saved sequence's settings.
        """
        return self._model(features.to(self.device), lengths)

    @torch.inference_mode()
    def predict_sequence(self, directory, *, max_frames=10000):
        """Validate and classify one saved whole-video sequence.

        Returns purpose, label_mapping, frames and positive_class_probability.
        load_features() enforces integrity and max_frames; extraction settings
        must match the checkpoint. Invalid or wholly missing features raise
        ValueError. Serving decides how that failure appears in the job result.
        """
        features, _, summary = load_features(directory, max_frames=max_frames)
        if feature_settings(summary) != self.feature_settings:
            raise ValueError("Sequence settings differ from the checkpoint")
        logits = self.predict_logits(
            features.unsqueeze(0), torch.tensor([len(features)])
        )
        return {
            "purpose": self.purpose,
            "positive_class_probability": logits.sigmoid().item(),
            "label_mapping": self.label_mapping,
            "frames": len(features),
        }
