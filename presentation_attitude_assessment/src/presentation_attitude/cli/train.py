"""Train a small GRU from a reviewed or synthetic-test sequence manifest."""

import argparse
from pathlib import Path

from presentation_attitude.pipelines.training import train


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--max-frames", type=int, default=10000)
    args = parser.parse_args()
    train(
        args.manifest,
        args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        hidden_size=args.hidden_size,
        learning_rate=args.learning_rate,
        seed=args.seed,
        device=args.device,
        max_frames=args.max_frames,
    )


if __name__ == "__main__":
    main()
