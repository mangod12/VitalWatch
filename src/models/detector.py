"""
Object detection layer using YOLOv8.
Detects person and optionally bed (if present in pretrained/custom model).
"""

from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np


@dataclass
class Detection:
    """Single detection: class name, bbox, confidence."""

    class_name: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int


class ObjectDetector:
    """
    YOLOv8-based object detector.
    Uses pretrained model for person (and bed if available).
    """

    PERSON_CLASS = "person"
    BED_CLASS = "bed"

    def __init__(self, model_path: str = "yolov8n.pt", device: Optional[str] = None):
        try:
            from ultralytics import YOLO
        except ImportError:
            raise ImportError("Install ultralytics: pip install ultralytics")
        self._model = YOLO(model_path)
        self._device = device  # None lets YOLO choose

    def run(self, frame: np.ndarray) -> List[Detection]:
        """
        Run detection on a BGR frame.
        Returns list of Detection (person, and bed if model supports it).
        """
        results = self._model(frame, device=self._device, verbose=False)
        out: List[Detection] = []
        for r in results:
            if r.boxes is None:
                continue
            names = r.names or {}
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                name = names.get(cls_id, "unknown")
                if name not in (self.PERSON_CLASS, self.BED_CLASS):
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                out.append(
                    Detection(
                        class_name=name,
                        confidence=conf,
                        x1=x1, y1=y1, x2=x2, y2=y2,
                    )
                )
        return out
