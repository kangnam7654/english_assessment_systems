"""Run one persistent local analysis worker, sharing PAA_DATA_DIR with the API."""

import argparse
import logging
import signal
import threading
from pathlib import Path

from presentation_attitude.serving.settings import Settings
from presentation_attitude.serving.worker import run_worker


def main():
    """Run the persistent analysis worker with exclusive local queue ownership."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--models", type=Path)
    parser.add_argument("--model-specs", type=Path)
    parser.add_argument(
        "--once", action="store_true", help="Process at most one queued job, then exit"
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    stop = threading.Event()

    def interrupt(signum, frame):
        # Exception unwinds the FFmpeg/MediaPipe contexts and marks the attempt failed.
        """Convert a termination signal into a request to stop the owned process loop.

        Args:
            signum: Signal number supplied by the operating system.
            frame: Interrupted Python stack frame.
        """
        stop.set()
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)

    def analyzer_factory():
        """Construct the worker's reusable video analyzer after lock acquisition.

        Returns:
            Reusable VideoAnalyzer initialized from the worker options.
        """
        from presentation_attitude.serving.analyzer import VideoAnalyzer

        return VideoAnalyzer(
            Settings.from_env(),
            checkpoint=args.checkpoint,
            device=args.device,
            models_dir=args.models,
            model_specs=args.model_specs,
        )

    try:
        run_worker(Settings.from_env(), analyzer_factory, stop, once=args.once)
    except KeyboardInterrupt:
        logging.info("Worker stopped; interrupted work can be retried")


if __name__ == "__main__":
    main()
