"""
Pose estimation using MediaPipe Pose.
Provides keypoints and derived posture/movement metrics.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import cv2
import numpy as np


@dataclass
class PoseResult:
    """Pose keypoints and derived metrics for one frame."""

    keypoints: Dict[str, tuple] = field(default_factory=dict)  # name -> (x, y) or (x, y, z)
    visibility: Dict[str, float] = field(default_factory=dict)
    # Derived
    posture: str = "unknown"  # standing, sitting, lying, unknown
    torso_angle: float = 0.0  # approximate torso angle from vertical (degrees)
    movement_intensity: float = 0.0  # 0-1 scale
    nose_y_normalized: float = 0.5  # 0=top, 1=bottom of frame
    hip_center_y: float = 0.5


class PoseEstimator:
    """
    MediaPipe Pose wrapper.
    Extracts keypoints and simple posture/movement metrics.
    """

    def __init__(self, min_detection_confidence: float = 0.5):
        try:
            import mediapipe as mp
        except ImportError:
            raise ImportError("Install mediapipe: pip install mediapipe")
        self._mp_pose = mp.solutions.pose
        self._pose = self._mp_pose.Pose(
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=0.5,
        )
        self._prev_landmarks: Optional[any] = None
        self._h, self._w = 0, 0

    def run(self, frame: np.ndarray) -> PoseResult:
        """
        Process BGR frame and return PoseResult with keypoints and metrics.
        """
        h, w = frame.shape[:2]
        self._h, self._w = h, w
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._pose.process(rgb)

        out = PoseResult()
        if not results.pose_landmarks:
            self._prev_landmarks = None
            return out

        lm = results.pose_landmarks.landmark
        # PoseLandmark enum: 0=NOSE, 11=LEFT_SHOULDER, 12=RIGHT_SHOULDER, 23=LEFT_HIP, 24=RIGHT_HIP, etc.
        landmark_names = [
            "NOSE", "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER", "RIGHT_EYE_INNER", "RIGHT_EYE", "RIGHT_EYE_OUTER",
            "LEFT_EAR", "RIGHT_EAR", "MOUTH_LEFT", "MOUTH_RIGHT", "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW",
            "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST", "LEFT_PINKY", "RIGHT_PINKY", "LEFT_INDEX", "RIGHT_INDEX",
            "LEFT_THUMB", "RIGHT_THUMB", "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE",
            "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
        ]
        keypoints = {}
        visibility = {}
        for i in range(min(len(lm), len(landmark_names))):
            p = lm[i]
            name = landmark_names[i]
            keypoints[name] = (p.x * w, p.y * h)
            visibility[name] = getattr(p, "visibility", 1.0)

        out.keypoints = keypoints
        out.visibility = visibility

        # Nose and hip for posture
        if "NOSE" in keypoints:
            out.nose_y_normalized = keypoints["NOSE"][1] / h
        left_hip = keypoints.get("LEFT_HIP", (w / 2, h / 2))
        right_hip = keypoints.get("RIGHT_HIP", (w / 2, h / 2))
        out.hip_center_y = (left_hip[1] + right_hip[1]) / 2 / h

        # Torso angle: shoulder midpoint to hip midpoint
        left_shoulder = keypoints.get("LEFT_SHOULDER", (w / 2, 0))
        right_shoulder = keypoints.get("RIGHT_SHOULDER", (w / 2, 0))
        shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
        hip_y = (left_hip[1] + right_hip[1]) / 2
        dx = (left_shoulder[0] + right_shoulder[0]) / 2 - (left_hip[0] + right_hip[0]) / 2
        dy = shoulder_y - hip_y
        if abs(dy) > 1:
            out.torso_angle = np.degrees(np.arctan2(abs(dx), abs(dy)))
        else:
            out.torso_angle = 0.0

        # Simple posture heuristic
        if out.torso_angle > 60 or out.nose_y_normalized > 0.75:
            out.posture = "lying"
        elif out.hip_center_y > 0.6 and out.nose_y_normalized < 0.5:
            out.posture = "sitting"
        else:
            out.posture = "standing"

        # Movement intensity from landmark change
        if self._prev_landmarks and len(lm) == len(self._prev_landmarks):
            total = 0.0
            for i in range(len(lm)):
                dx = lm[i].x - self._prev_landmarks[i][0]
                dy = lm[i].y - self._prev_landmarks[i][1]
                total += np.sqrt(dx * dx + dy * dy)
            out.movement_intensity = min(1.0, total / 5.0)  # scale
        self._prev_landmarks = [(p.x, p.y) for p in lm]

        return out

    def close(self) -> None:
        self._pose.close()
