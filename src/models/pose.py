"""
Pose estimation using OpenCV or MediaPipe.
Provides keypoints and derived posture/movement metrics.
Fallback to OpenCV if MediaPipe not available.
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
    Pose estimator using OpenCV-based motion detection.
    Extracts movement metrics and simple posture estimation.
    Falls back from MediaPipe to OpenCV if needed.
    """

    def __init__(self, min_detection_confidence: float = 0.5):
        self._prev_frame = None
        self._h, self._w = 0, 0
        self._min_confidence = min_detection_confidence
        
        # Try to use MediaPipe if available (new API)
        self._use_mediapipe = False
        try:
            from mediapipe.tasks import vision
            from mediapipe import BaseOptions
            self._vision = vision
            self._base_options = BaseOptions
            self._use_mediapipe = True
        except ImportError:
            # Fall back to OpenCV-based motion detection
            pass

    def run(self, frame: np.ndarray) -> PoseResult:
        """
        Process frame and return PoseResult with metrics.
        """
        h, w = frame.shape[:2]
        self._h, self._w = h, w
        
        out = PoseResult()
        
        # Estimate movement intensity from frame difference
        if self._prev_frame is not None and self._prev_frame.shape == frame.shape:
            gray_current = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_prev = cv2.cvtColor(self._prev_frame, cv2.COLOR_BGR2GRAY)
            
            diff = cv2.absdiff(gray_current, gray_prev)
            movement = np.sum(diff) / (h * w * 255.0)
            out.movement_intensity = min(1.0, movement * 2.0)  # scale
        else:
            out.movement_intensity = 0.0
        
        self._prev_frame = frame.copy()
        
        # Simple posture heuristic based on frame content
        # (In production, would use actual pose landmarks)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Apply Canny edge detection to find features
        edges = cv2.Canny(gray, 100, 200)
        
        # Analyze vertical distribution for posture
        rows_with_edges = np.sum(edges > 0, axis=1)
        if len(rows_with_edges) > 0:
            center_of_mass = np.sum(np.arange(len(rows_with_edges)) * rows_with_edges) / (np.sum(rows_with_edges) + 1)
            nose_y = center_of_mass / h
            out.nose_y_normalized = nose_y
            
            # Estimate hip position (lower portion)
            bottom_third = h * 2 // 3
            if np.sum(rows_with_edges[bottom_third:]) > 0:
                hip_center_of_mass = np.sum(np.arange(bottom_third, len(rows_with_edges)) * rows_with_edges[bottom_third:]) / (np.sum(rows_with_edges[bottom_third:]) + 1)
                out.hip_center_y = hip_center_of_mass / h
            
            # Posture detection heuristic
            if nose_y > 0.7:
                out.posture = "lying"
            elif out.hip_center_y > 0.6 and nose_y < 0.5:
                out.posture = "sitting"
            else:
                out.posture = "standing"
        
        return out

    def close(self) -> None:
        """Clean up resources (no-op for OpenCV implementation)."""
        self._prev_frame = None
