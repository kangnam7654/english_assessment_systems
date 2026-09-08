"""Evaluate a checkpoint on a test manifest, excluding its training/validation data."""

import argparse
from pathlib import Path

from presentation_attitude.pipelines.evaluation import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--manifest", type=Path, required=True, help="Test-only manifest"
    )
    parser.add_argument(
        "--training-manifest",
        type=Path,
        required=True,
        help="Original training/validation manifest for leakage checks",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--device", choices=("auto", "cpu", "mps"), default="auto")
    parser.add_argument("--max-frames", type=int, default=10000)
    args = parser.parse_args()
    report = evaluate(
        args.checkpoint,
        args.manifest,
        args.training_manifest,
        args.output,
        threshold=args.threshold,
        device=args.device,
        max_frames=args.max_frames,
    )
    print(
        f"Evaluation complete ({report['purpose']}, {report['device']}): {report['metrics']['samples']} samples; accuracy={report['metrics']['accuracy']:.4f}; F1={report['metrics']['f1']}; ROC-AUC={report['metrics']['roc_auc']}. {report['notice']}"
    )


if __name__ == "__main__":
    main()
