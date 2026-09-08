"""Start the local upload/status API; launch presentation-worker separately."""

import argparse

import uvicorn

from presentation_attitude.paths import workspace_root
from presentation_attitude.serving.api import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", type=int, default=43187, help="API port (default: 43187)"
    )
    args = parser.parse_args()
    ui_dir = workspace_root() / "presentation_attitude_assessment/frontend/dist"
    uvicorn.run(
        create_app(ui_dir=ui_dir if (ui_dir / "index.html").is_file() else None),
        host="127.0.0.1",
        port=args.port,
    )


if __name__ == "__main__":
    main()
