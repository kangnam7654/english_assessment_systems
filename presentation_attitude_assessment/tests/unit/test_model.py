"""Regression checks for model."""

import unittest

import torch

from presentation_attitude.data.dataset import collate_sequences
from presentation_attitude.models.gru import GRUClassifier
from presentation_attitude.schema import INPUT_SIZE


class ModelTests(unittest.TestCase):
    """Exercise model tests behavior with controlled fixtures."""
    def test_padding_does_not_change_logits_or_mix_video_state(self):
        """Verify padding does not change logits or mix video state."""
        torch.manual_seed(7)
        model = GRUClassifier(8).eval()
        short, long = torch.randn(3, INPUT_SIZE), torch.randn(7, INPUT_SIZE)
        samples = [
            {
                "features": x,
                "timestamps_ms": torch.arange(len(x)) * 200,
                "label": i,
                "id": str(i),
            }
            for i, x in enumerate((short, long))
        ]
        batch = collate_sequences(samples)
        with torch.inference_mode():
            before = model(short[None], torch.tensor([3]))
            grouped = model(batch["features"], batch["lengths"])
            # Garbage in padding must have no influence on the last real state.
            batch["features"][0, 3:] = 9999
            changed_padding = model(batch["features"], batch["lengths"])
            model(long[None], torch.tensor([7]))
            after = model(short[None], torch.tensor([3]))
        torch.testing.assert_close(before[0], grouped[0])
        torch.testing.assert_close(grouped, changed_padding, rtol=0, atol=0)
        torch.testing.assert_close(before, after, rtol=0, atol=0)
        self.assertEqual(
            batch["padding_mask"].tolist(), [[False] * 3 + [True] * 4, [False] * 7]
        )

    def test_real_missing_frame_is_not_padding(self):
        """Verify real missing frame is not padding."""
        values = torch.zeros(4, INPUT_SIZE)
        values[0, -3:] = 1
        batch = collate_sequences(
            [
                {
                    "features": values,
                    "timestamps_ms": torch.arange(4) * 200,
                    "id": "missing",
                    "label": 0,
                }
            ]
        )
        self.assertEqual(batch["lengths"].tolist(), [4])
        self.assertFalse(batch["padding_mask"].any())
        model = GRUClassifier(8)
        logits = model(batch["features"], batch["lengths"])
        torch.nn.functional.binary_cross_entropy_with_logits(
            logits, batch["labels"]
        ).backward()
        self.assertTrue(
            all(
                p.grad is not None and torch.isfinite(p.grad).all()
                for p in model.parameters()
            )
        )
