"""Local video -> FFmpeg RGB24 stdout -> independent NumPy frames, without files."""

import json
import math
import subprocess
import threading
from collections import deque
from pathlib import Path

import numpy as np


class VideoDecodeError(RuntimeError):
    """Report FFmpeg startup, truncated-frame, or decoding failures."""
    pass


def read_frame_bytes(stream, size):
    """Pipe reads may be short. Only an empty frame at EOF is a clean boundary.

    Args:
        stream: Open stream owned by the caller.
        size: Expected raw frame size in bytes.

    Returns:
        Exactly size bytes, or empty bytes for clean EOF before a new frame.

    Raises:
        VideoDecodeError: EOF arrives after only part of the expected frame.
    """
    chunks, remaining = [], size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if remaining == size:
                return None
            raise VideoDecodeError(
                f"Truncated RGB frame: {size - remaining}/{size} bytes"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class FFmpegVideoReader:
    """Single-use context-managed iterator yielding RGB uint8 arrays (H, W, 3).

    FPS timestamps are a resampled grid, not original PTS. Use a `with` block so
    exceptions and an early `break` also reap FFmpeg. Frames own immutable bytes
    and remain valid after advancing/closing; copy a frame before modifying it.
    """

    def __init__(
        self,
        path,
        *,
        fps=5,
        start_seconds=0,
        duration_seconds=None,
        allowed_formats=None,
        max_pixels=None,
    ):
        """Validate sampling options and initialize a single-use FFmpeg reader.

        Args:
            path: Filesystem path to the input or output artifact.
            fps: Frames per second on the FFmpeg resampling grid.
            start_seconds: Start offset in seconds on the input video.
            duration_seconds: Optional interval duration in seconds.
            allowed_formats: Optional comma-separated FFmpeg input format whitelist.
            max_pixels: Optional upper bound on decoded frame area.

        Raises:
            FileNotFoundError: Required path is missing or already exists: self.path.
            ValueError: fps must be finite and in (0, 1000]; start_seconds must be finite
                and nonnegative; duration_seconds must be positive and finite.
        """
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        if not math.isfinite(fps) or not 0 < fps <= 1000:
            raise ValueError("fps must be finite and in (0, 1000]")
        if not math.isfinite(start_seconds) or start_seconds < 0:
            raise ValueError("start_seconds must be finite and nonnegative")
        if duration_seconds is not None and (
            not math.isfinite(duration_seconds) or duration_seconds <= 0
        ):
            raise ValueError("duration_seconds must be positive and finite")
        self.fps, self.start_seconds, self.duration_seconds = (
            fps,
            start_seconds,
            duration_seconds,
        )
        self.process = None
        self.input_options = (
            ["-protocol_whitelist", "file,pipe", "-format_whitelist", allowed_formats]
            if allowed_formats
            else []
        )
        self.max_pixels = max_pixels
        self.frame_count = 0
        self.width = self.height = None
        self.command = None
        self._closed = False
        self._stderr = deque(maxlen=16)  # At most 64 KiB; always drain the pipe.
        self._stderr_thread = None

    def __enter__(self):
        """Probe the video and start an FFmpeg process streaming raw RGB frames.

        Returns:
            This initialized context-managed resource.

        Raises:
            RuntimeError: Reader is single-use.
            VideoDecodeError: Input has no video stream; Only quarter-turn rotation metadata
                is supported; Invalid video dimensions; Video exceeds decoded pixel limit.
        """
        if self.process is not None or self._closed:
            raise RuntimeError("Reader is single-use")
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                *self.input_options,
                "-select_streams",
                "v:0",
                "-show_streams",
                "-of",
                "json",
                str(self.path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode:
            raise VideoDecodeError(f"ffprobe failed: {probe.stderr[-4096:]}")
        streams = json.loads(probe.stdout)["streams"]
        if not streams:
            raise VideoDecodeError("Input has no video stream")
        info = streams[0]
        self.width, self.height = int(info["width"]), int(info["height"])
        rotation = float(info.get("tags", {}).get("rotate", 0))
        for data in info.get("side_data_list", []):
            if "rotation" in data:
                rotation = float(data["rotation"])
        if not math.isfinite(rotation) or not math.isclose(
            rotation / 90, round(rotation / 90), abs_tol=1e-6
        ):
            raise VideoDecodeError("Only quarter-turn rotation metadata is supported")
        if round(rotation / 90) % 2:
            self.width, self.height = self.height, self.width
        if min(self.width, self.height) <= 0:
            raise VideoDecodeError("Invalid video dimensions")
        if self.max_pixels is not None and self.width * self.height > self.max_pixels:
            raise VideoDecodeError("Video exceeds decoded pixel limit")
        self.command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-xerror",
            "-ss",
            str(self.start_seconds),
            *self.input_options,
            "-i",
            str(self.path),
        ]
        if self.duration_seconds is not None:
            self.command += ["-t", str(self.duration_seconds)]
        # Identity scale for fixed-resolution inputs; fixes framing if resolution
        # changes midstream, since rawvideo has no per-frame dimension headers.
        self.command += [
            "-map",
            "0:v:0",
            "-an",
            "-sn",
            "-dn",
            "-vf",
            f"fps=fps={self.fps}:start_time=0,scale={self.width}:{self.height}",
            "-fps_mode",
            "passthrough",
            "-pix_fmt",
            "rgb24",
            "-c:v",
            "rawvideo",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        try:
            self._stderr_thread.start()
        except BaseException:
            self.close()
            raise
        return self

    def _drain_stderr(self):
        """Drain FFmpeg diagnostics in a background thread to prevent pipe blockage."""
        while chunk := self.process.stderr.read(4096):
            self._stderr.append(chunk)

    def __iter__(self):
        """Return this reader after verifying it was opened in a context manager.

        Returns:
            This opened reader instance.

        Raises:
            RuntimeError: Use FFmpegVideoReader in a with block.
        """
        if self.process is None:
            raise RuntimeError("Use FFmpegVideoReader in a with block")
        return self

    def __next__(self):
        """Read the next owned RGB frame and verify decoder completion at EOF.

        Returns:
            Next decoded RGB uint8 frame of shape (H, W, 3).

        Raises:
            RuntimeError: Use FFmpegVideoReader in a with block.
            VideoDecodeError: FFmpeg produced no sampled frames.
        """
        if self._closed:
            raise StopIteration
        if self.process is None:
            raise RuntimeError("Use FFmpegVideoReader in a with block")
        try:
            payload = read_frame_bytes(
                self.process.stdout, self.width * self.height * 3
            )
            if payload is None:
                returncode = self.process.wait(timeout=10)
                self.close()
                if returncode:
                    detail = b"".join(self._stderr).decode("utf-8", errors="replace")
                    raise VideoDecodeError(f"FFmpeg exited with {returncode}: {detail}")
                if self.frame_count == 0:
                    raise VideoDecodeError("FFmpeg produced no sampled frames")
                raise StopIteration
            frame = np.frombuffer(payload, dtype=np.uint8).reshape(
                self.height, self.width, 3
            )
            self.frame_count += 1
            return frame
        except BaseException:
            self.close()
            raise

    def close(self):
        """Reap the subprocess and close its pipes; repeated calls are harmless."""
        if self._closed:
            return
        self._closed = True
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        finally:
            self.process.stdout.close()
            if (
                self._stderr_thread is not None
                and self._stderr_thread.ident is not None
            ):
                self._stderr_thread.join(timeout=3)
            self.process.stderr.close()

    def __exit__(self, exc_type, exc_value, traceback):
        """Close pipes and reap FFmpeg when leaving the reader context.

        Args:
            exc_type: Exception type supplied by the context manager protocol, if any.
            exc_value: Exception instance supplied by the context manager protocol, if any.
            traceback: Traceback supplied by the context manager protocol, if any.
        """
        self.close()
