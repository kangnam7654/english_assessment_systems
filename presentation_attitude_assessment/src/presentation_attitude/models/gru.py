"""Small video-level GRU architecture."""

from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence

from presentation_attitude.schema import INPUT_SIZE


class GRUClassifier(nn.Module):
    """Map variable-length landmark sequences to one binary logit per video.

    This module owns network structure only. Checkpoint loading, devices and
    inference mode belong to ClassifierRuntime; optimization belongs to train().
    """

    def __init__(self, hidden_size=32):
        super().__init__()
        self.config = {"hidden_size": hidden_size}
        self.gru = nn.GRU(INPUT_SIZE, hidden_size, batch_first=True)
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, features, lengths):
        """Return logits (B,) from features (B, T, INPUT_SIZE) and lengths (B,).

        lengths contains positive unpadded lengths. Packing ignores right padding;
        no recurrent state is retained between calls. Apply sigmoid to obtain the
        positive-class model output, not a calibrated confidence score.
        """
        packed = pack_padded_sequence(
            features, lengths.cpu(), batch_first=True, enforce_sorted=False
        )
        # No hidden state is passed in or retained: every video starts at zero.
        _, hidden = self.gru(packed)
        return self.head(hidden[-1]).squeeze(-1)
