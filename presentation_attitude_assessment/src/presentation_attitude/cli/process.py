"""Extract a whole video's landmarks, masks and preprocessed coordinates."""

import argparse
from pathlib import Path

from presentation_attitude.pipelines.extraction import process_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory"
    )
    parser.add_argument("--fps", type=float, default=5)
    parser.add_argument(
        "--window", type=int, default=3, help="Positive odd centered smoothing window"
    )
    parser.add_argument(
        "--models", type=Path, help="Model cache; defaults to the workspace cache"
    )
    parser.add_argument(
        "--model-specs",
        type=Path,
        help="Pinned model spec JSON; defaults to workspace configs",
    )
    args = parser.parse_args()
    result = process_video(
        args.video,
        args.output,
        fps=args.fps,
        window=args.window,
        models_dir=args.models,
        model_specs=args.model_specs,
    )
    print(
        f"Complete: {result['sampled_frames']} sampled frames → {args.output / result['sequence_file']}"
    )


if __name__ == "__main__":
    main()
