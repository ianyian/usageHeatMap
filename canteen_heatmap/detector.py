"""YOLO person detector wrapper (§4.2).

Loads a nano YOLO model, runs inference on a frame, filters to the `person` class and
the configured confidence threshold, and returns normalized foot-points. Nothing else
in the system knows the detector is YOLO.
"""
from typing import List, Tuple

import numpy as np

MODEL_NAME = "yolo11n.pt"
PERSON_CLASS = 0  # COCO class id for "person"
# Inference input size; smaller = faster. 480 keeps nano-model latency sane on CPU.
IMG_SIZE = 480

# (x, y, confidence) — x/y normalized 0..1, foot-point (bottom-center of bbox).
Detection = Tuple[float, float, float]


class PersonDetector:
    def __init__(self, model_name: str = MODEL_NAME):
        from ultralytics import YOLO  # deferred: import is slow, keep startup visible

        self.model = YOLO(model_name)

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float) -> List[Detection]:
        h, w = frame_bgr.shape[:2]
        results = self.model.predict(
            frame_bgr,
            imgsz=IMG_SIZE,
            conf=conf_threshold,
            classes=[PERSON_CLASS],
            verbose=False,
        )
        people: List[Detection] = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            # Foot-point: bottom-center of the bbox — maps to the floor plane far
            # better than bbox center for an overhead-ish heatmap (§4.2).
            foot_x = ((x1 + x2) / 2.0) / w
            foot_y = y2 / h
            people.append((min(1.0, max(0.0, foot_x)), min(1.0, max(0.0, foot_y)), conf))
        return people
