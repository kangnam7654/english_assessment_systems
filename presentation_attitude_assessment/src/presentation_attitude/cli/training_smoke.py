"""Check the training pipeline with artificial coordinate sequences on CPU."""

import argparse
from pathlib import Path

from presentation_attitude.pipelines.training_smoke import run_smoke


def main():
    """Run a synthetic sequence training check without attitude-quality claims."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = run_smoke(args.output, epochs=args.epochs, seed=args.seed)
    print(
        f"Synthetic pipeline check complete: {result['optimizer_steps']} optimizer steps; no attitude performance claim."
    )


if __name__ == "__main__":
    main()
