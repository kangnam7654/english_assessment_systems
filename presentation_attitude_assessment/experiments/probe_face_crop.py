"""Controlled, manually selected crop diagnostic; not an automatic preprocessing stage."""

import argparse
import json
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions, vision

from presentation_attitude.artifacts import write_json
from presentation_attitude.models.assets import get_models
from presentation_attitude.paths import workspace_root

ROOT = workspace_root()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    specs = [
        ("lecturer2_sweep", "000001.png", [330, 0, 470, 140]),
        ("lecturer3_throw", "000006.png", [285, 35, 425, 175]),
        ("lecture_05pct", "000001.png", [310, 0, 450, 140]),
        ("lecturer1_pray", "000001.png", [290, 10, 480, 200]),
        ("lecture_20pct", "000001.png", [250, 80, 390, 220]),
    ]
    model_dir = ROOT / ".local-data/presentation-attitude/models"
    models = get_models(
        model_dir, ROOT / "presentation_attitude_assessment/configs/models.json"
    )
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path=str(model_dir / "face_landmarker.task"),
            delegate=BaseOptions.Delegate.CPU,
        ),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    rows = []
    with vision.FaceLandmarker.create_from_options(options) as task:
        for interval, filename, box in specs:
            path = args.audit / interval / "frames" / filename
            bgr = cv2.imread(str(path))
            if bgr is None:
                raise ValueError(f"Unreadable frame: {path}")
            x1, y1, x2, y2 = box
            row = {"interval": interval, "frame": filename, "manual_crop_xyxy": box}
            for name, frame in [
                ("full_frame", bgr),
                ("manual_crop", bgr[y1:y2, x1:x2]),
            ]:
                image = mp.Image(
                    image_format=mp.ImageFormat.SRGB,
                    data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                )
                row[name + "_face_detected"] = bool(task.detect(image).face_landmarks)
            rows.append(row)
    write_json(
        args.output,
        {
            "purpose": "manual_crop_diagnostic_not_training_data",
            "running_mode": "IMAGE",
            "models": models,
            "cases": rows,
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
