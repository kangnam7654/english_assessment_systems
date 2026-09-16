"""Render raw vs smoothed landmark overlays for intervals with usable features."""

import argparse
from pathlib import Path

from presentation_attitude.evaluation.visualization import render_comparison


def main():
    """Render before/after landmark overlays for a completed audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render_comparison(args.audit, args.processed, args.output)


if __name__ == "__main__":
    main()
