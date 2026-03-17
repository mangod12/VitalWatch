"""
Distress detection using a pre-trained Keras CNN model.
Detects faces via Haar cascade, predicts distress probability,
and classifies into Normal / Warning / Critical with smoothing.
"""

import logging
import os
import traceback
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

import cv2
import numpy as np

# Suppress TF warnings early, before any import
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

logger = logging.getLogger("vitalwatch.distress")


@dataclass
class FaceDetection:
    """A detected face with its bounding box."""
    x: int
    y: int
    w: int
    h: int
    distress_score: float = 0.0


@dataclass
class DistressResult:
    """Result of distress detection on a single frame."""
    distress_score: float  # 0-1, smoothed
    level: str  # "NORMAL", "WARNING", "CRITICAL"
    faces: List[FaceDetection] = field(default_factory=list)
    raw_score: float = 0.0  # un-smoothed score from current frame

    def to_dict(self) -> dict:
        return {
            "distress_score": round(self.distress_score, 3),
            "level": self.level,
            "face_count": len(self.faces),
            "raw_score": round(self.raw_score, 3),
            "faces": [
                {"x": f.x, "y": f.y, "w": f.w, "h": f.h, "score": round(f.distress_score, 3)}
                for f in self.faces
            ],
        }


class DistressDetector:
    """
    Face-based distress detection using a Keras CNN model.

    Loads a pre-trained model that takes 48x48 grayscale face crops
    and outputs distress probability. Applies exponential smoothing
    across frames to reduce jitter.
    """

    def __init__(self, model_path: str = "distress_model.h5", smoothing: float = 0.2):
        """
        Args:
            model_path: Path to the Keras .h5 model file.
            smoothing: Smoothing factor (alpha) for exponential moving average.
                       Lower = smoother but slower to react. Default 0.2.
        """
        self._model = None
        self._model_path = model_path
        self._smoothing = smoothing
        self._previous_score = 0.0
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        self._load_model()

    def _load_model(self):
        """Load TensorFlow and the Keras model."""
        try:
            print(f"[DistressDetector] Importing TensorFlow...")
            # Ensure user site-packages is on sys.path (python -m can miss it)
            import sys, site
            user_site = site.getusersitepackages()
            if user_site not in sys.path:
                sys.path.insert(0, user_site)
            import tensorflow as tf
            print(f"[DistressDetector] TensorFlow {tf.__version__} imported OK")

            print(f"[DistressDetector] Loading model from: {os.path.abspath(self._model_path)}")
            if not os.path.exists(self._model_path):
                print(f"[DistressDetector] ERROR: Model file not found: {os.path.abspath(self._model_path)}")
                self._model = None
                return

            self._model = tf.keras.models.load_model(self._model_path)
            # Recompile to suppress metrics warning
            self._model.compile(
                optimizer="adam",
                loss="categorical_crossentropy",
                metrics=["accuracy"],
            )
            print(f"[DistressDetector] Model loaded successfully (input shape: {self._model.input_shape})")
            logger.info("Distress model loaded from %s (input shape: %s)",
                        self._model_path, self._model.input_shape)
        except Exception as e:
            print(f"[DistressDetector] FAILED to load: {e}")
            traceback.print_exc()
            logger.error("Failed to load distress model from '%s': %s", self._model_path, e)
            self._model = None

    @property
    def is_available(self) -> bool:
        """Whether the model loaded successfully."""
        return self._model is not None

    @staticmethod
    def _preprocess_face(face_bgr: np.ndarray) -> np.ndarray:
        """Convert a face crop to the model's expected input format."""
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (48, 48))
        normalized = resized / 255.0
        return normalized.reshape(1, 48, 48, 1)

    def detect(self, frame: np.ndarray) -> DistressResult:
        """
        Run distress detection on a video frame.

        Args:
            frame: BGR image (OpenCV format).

        Returns:
            DistressResult with smoothed score, level, and face detections.
        """
        if not self.is_available:
            return DistressResult(
                distress_score=0.0,
                level="NORMAL",
                raw_score=0.0,
            )

        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_rects = self._face_cascade.detectMultiScale(gray_frame, 1.3, 5)

        faces: List[FaceDetection] = []
        max_distress = 0.0

        for (x, y, w, h) in face_rects:
            face_crop = frame[y:y + h, x:x + w]
            if face_crop.size == 0:
                continue

            input_tensor = self._preprocess_face(face_crop)
            prediction = self._model.predict(input_tensor, verbose=0)
            distress_prob = float(prediction[0][0])

            faces.append(FaceDetection(
                x=int(x), y=int(y), w=int(w), h=int(h),
                distress_score=distress_prob,
            ))
            max_distress = max(max_distress, distress_prob)

        # Exponential smoothing on the maximum distress across all faces
        smoothed = (1 - self._smoothing) * self._previous_score + self._smoothing * max_distress
        self._previous_score = smoothed

        # Classify severity level
        if smoothed >= 0.8:
            level = "CRITICAL"
        elif smoothed >= 0.5:
            level = "WARNING"
        else:
            level = "NORMAL"

        return DistressResult(
            distress_score=smoothed,
            level=level,
            faces=faces,
            raw_score=max_distress,
        )

    def draw_overlays(self, frame: np.ndarray, result: DistressResult) -> np.ndarray:
        """Draw face bounding boxes and distress labels on the frame."""
        color_map = {
            "CRITICAL": (0, 0, 255),    # Red
            "WARNING": (0, 255, 255),    # Yellow
            "NORMAL": (0, 255, 0),       # Green
        }
        color = color_map.get(result.level, (0, 255, 0))

        for face in result.faces:
            cv2.rectangle(frame, (face.x, face.y),
                          (face.x + face.w, face.y + face.h), color, 2)
            label = f"Distress: {result.level} ({result.distress_score:.2f})"
            cv2.putText(frame, label, (face.x, face.y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        return frame
