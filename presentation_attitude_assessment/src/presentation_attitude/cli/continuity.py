"""Report sampled runs without treating detector absence as an attitude label."""

import argparse
from pathlib import Path

from presentation_attitude.evaluation.diagnostics import report_continuity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report_continuity(args.audit, args.processed, args.output)


if __name__ == "__main__":
    main()
