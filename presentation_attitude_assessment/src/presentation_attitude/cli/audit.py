"""Audit detector availability, never infer an attitude label from missing landmarks."""

import argparse
from pathlib import Path

from presentation_attitude.paths import workspace_root
from presentation_attitude.vision.landmarks import run_audit


def main():
    """Extract planned video intervals and write landmark diagnostics."""
    root = workspace_root()
    module_root = root / "presentation_attitude_assessment"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", type=Path, default=module_root / "configs/audit_intervals.json"
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=module_root / "docs/data/sample_inventory.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New directory; existing output is refused",
    )
    parser.add_argument(
        "--models", type=Path, default=root / ".local-data/presentation-attitude/models"
    )
    parser.add_argument(
        "--save-frames",
        action="store_true",
        help="Save diagnostic PNG copies after inference; never used as detector input",
    )
    args = parser.parse_args()
    run_audit(
        root, args.plan, args.inventory, args.output, args.models, args.save_frames
    )


if __name__ == "__main__":
    main()
