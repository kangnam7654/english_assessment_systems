"""Start the local Mock API and Next.js UI; Ctrl+C stops both process groups."""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time

from writing_synthesis.paths import PROJECT_DIR

MODULE = PROJECT_DIR


def main() -> None:
    """Start the local Mock API and Next.js UI with coordinated shutdown."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, default=18741)
    parser.add_argument("--ui-port", type=int, default=18742)
    args = parser.parse_args()
    if args.api_port == args.ui_port:
        parser.error("API and UI ports must differ.")
    for port in (args.api_port, args.ui_port):
        if not 1024 <= port <= 65535:
            parser.error("Choose ports between 1024 and 65535.")
        with socket.socket() as listener:
            # Allow restart after a closed connection enters TIME_WAIT; an active
            # listener still prevents binding to its port.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                parser.error(
                    f"Port {port} is occupied. Choose an explicit alternative port."
                )
    npm = shutil.which("npm")
    if npm is None or not (MODULE / "frontend/node_modules/next").exists():
        parser.error(
            "Install Node.js and run npm ci in writing_data_synthesis/frontend first."
        )
    env = {
        **os.environ,
        "WDS_LLM_MODE": "mock",
        "WDS_API_URL": f"http://127.0.0.1:{args.api_port}",
    }
    commands = [
        (
            [
                sys.executable,
                "-m",
                "uvicorn",
                "writing_synthesis.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ],
            MODULE,
        ),
        (
            [
                npm,
                "run",
                "dev",
                "--",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(args.ui_port),
            ],
            MODULE / "frontend",
        ),
    ]
    children = []

    def stop(_signal, _frame):
        """Convert a termination signal into a request to stop the owned process loop.

        Args:
            _signal: Signal number supplied by the operating system.
            _frame: Interrupted Python stack frame; unused.
        """
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        for command, cwd in commands:
            children.append(
                subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True)
            )
        print(
            f"Starting Mock UI: http://127.0.0.1:{args.ui_port} (Ctrl+C stops API and UI)",
            flush=True,
        )
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        raise SystemExit("A service exited; stopping the local UI environment.")
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()


if __name__ == "__main__":
    main()
