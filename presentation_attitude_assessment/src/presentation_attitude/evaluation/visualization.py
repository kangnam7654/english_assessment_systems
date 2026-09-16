"""Landmark previews and raw-versus-preprocessed overlays."""

import math
import subprocess

import cv2
import numpy as np

from presentation_attitude.artifacts import iter_jsonl, read_json
from presentation_attitude.data.preprocessing import restore_xy
from presentation_attitude.schema import PARTS


def contact_sheet(frames, rows, output):
    # RGB previews were retained during inference; no frame files are read.
    """Write a labeled grid of sampled frames and detection counts.

    Args:
        frames: Frame image paths used to build the visual diagnostic.
        rows: Ordered per-frame landmark records.
        output: Destination directory or file for generated artifacts.
    """
    tiles = []
    for i in sorted(frames):
        frame = cv2.cvtColor(frames[i], cv2.COLOR_RGB2BGR)
        height, width = frame.shape[:2]
        row = rows[i]
        for points, color in [(row["face_landmarks"], (70, 255, 70))] + [
            (hand["landmarks"], (0, 165, 255)) for hand in row["hands"]
        ]:
            for x, y, _ in points:
                cv2.circle(frame, (round(x * width), round(y * height)), 1, color, -1)
        tile = np.zeros((400, 640, 3), np.uint8)
        tile[:360] = cv2.resize(frame, (640, 360))
        caption = (
            f"t~{row['source_grid_seconds']:.2f}s  "
            f"face={int(row['face_present'])} hands={row['hand_count']}"
        )
        cv2.putText(
            tile,
            caption,
            (8, 386),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        tiles.append(tile)
    sheet = np.full((math.ceil(len(tiles) / 3) * 400, 1920, 3), 35, np.uint8)
    for i, tile in enumerate(tiles):
        y, x = (i // 3) * 400, (i % 3) * 640
        sheet[y : y + 400, x : x + 640] = tile
    if not cv2.imwrite(str(output), sheet):
        raise OSError(f"Cannot write {output}")


def draw_points(image, xy, color):
    """Draw visible normalized landmarks into an image buffer.

    Args:
        image: Image buffer to draw into.
        xy: Two-dimensional landmark coordinates.
        color: Drawing color in the target image's channel order.
    """
    height, width = image.shape[:2]
    for x, y in xy:
        # Ignore out-of-frame points for drawing, but retain them in the data.
        if 0 <= x < 1 and 0 <= y < 1:
            cv2.circle(image, (round(x * width), round(y * height)), 1, color, -1)


def render_comparison(audit_dir, processed_dir, output):
    """Render raw, normalized, and smoothed landmark diagnostics for audit intervals.

    Args:
        audit_dir: Directory containing the completed landmark audit.
        processed_dir: Directory containing normalized and smoothed audit records.
        output: Destination directory or file for generated artifacts.

    Raises:
        ValueError: Preprocessing must be complete.
    """
    summary = read_json(processed_dir / "summary.json")
    if summary["status"] != "complete":
        raise ValueError("Preprocessing must be complete")
    output.mkdir(parents=True, exist_ok=False)
    for interval in summary["intervals"]:
        if not any(interval["parts"][p]["valid_frames"] for p in PARTS):
            continue
        key = interval["id"]
        rows = list(iter_jsonl(processed_dir / f"{key}.jsonl"))
        destination = output / key
        destination.mkdir()
        tiles = []
        for i, row in enumerate(rows):
            bgr = cv2.imread(str(audit_dir / key / "frames" / f"{i + 1:06d}.png"))
            if bgr is None:
                raise ValueError(
                    f"Missing diagnostic image: {key}/{i}. Run presentation-audit with --save-frames for full comparison videos."
                )
            raw, smooth = bgr.copy(), bgr.copy()
            if row["raw"]["face_present"]:
                draw_points(
                    raw, np.asarray(row["raw"]["face_landmarks"])[:, :2], (70, 255, 70)
                )
            for hand in row["raw"]["hands"]:
                draw_points(raw, np.asarray(hand["landmarks"])[:, :2], (0, 165, 255))
            for part in PARTS:
                if row["valid"][part]:
                    xy = restore_xy(
                        row["smoothed_xy"][part],
                        np.array([interval["width"], interval["height"]]),
                        row["anchor"],
                    )
                    draw_points(
                        smooth, xy, (70, 255, 70) if part == "face" else (0, 165, 255)
                    )
            tile = np.zeros((420, 1280, 3), dtype=np.uint8)
            tile[:360, :640] = cv2.resize(raw, (640, 360))
            tile[:360, 640:] = cv2.resize(smooth, (640, 360))
            for text, position in [
                (f"RAW   t~{row['raw']['source_grid_seconds']:.2f}s", (10, 382)),
                ("NORMALIZED + MEAN, restored to original frame", (650, 382)),
                ("Face=green, hands=orange", (10, 405)),
                (
                    "Support F/L/R: "
                    + "/".join(str(row["smoothing_support"][p]) for p in PARTS)
                    + "  (0 = unavailable)",
                    (650, 405),
                ),
            ]:
                cv2.putText(
                    tile,
                    text,
                    position,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            if not cv2.imwrite(str(destination / f"{i + 1:06d}.jpg"), tile):
                raise OSError("Cannot save comparison frame")
            tiles.append(tile)
        for offset in range(0, len(tiles), 3):
            if not cv2.imwrite(
                str(destination / f"sheet_{offset // 3 + 1}.jpg"),
                np.vstack(tiles[offset : offset + 3]),
            ):
                raise OSError("Cannot save comparison sheet")
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-framerate",
                str(summary["sample_fps"]),
                "-i",
                str(destination / "%06d.jpg"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(destination / "comparison.mp4"),
            ],
            check=True,
        )
        print(key, len(tiles), "comparison frames rendered")
