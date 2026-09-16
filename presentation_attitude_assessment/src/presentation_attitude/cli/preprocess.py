"""Face-relative XY features with explicit missingness; no detector or classifier."""

import argparse
from pathlib import Path

from presentation_attitude.data.preprocessing import preprocess_audit


def main():
    """Normalize and smooth landmarks from a completed interval audit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--window", type=int, default=3)
    args = parser.parse_args()
    preprocess_audit(args.audit, args.output, args.window)


if __name__ == "__main__":
    main()
