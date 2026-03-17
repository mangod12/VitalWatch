"""
Rule-based event detection for patient monitoring.
Detects: fall, bed_exit, immobility, abnormal_movement.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional

from ..models.detector import Detection
from ..models.pose import PoseResult


@dataclass
class DetectedEvent:
    event_type: str
    confidence: float
    timestamp: float
    metadata: dict = field(default_factory=dict)


class EventEngine:
    """
    Rule-based event detection from detection + pose + motion.
    MVP: no heavy training; thresholds tuned for demo.
    """

    EVENT_FALL = "fall"
    EVENT_BED_EXIT = "bed_exit"
    EVENT_IMMOBILITY = "immobility"
    EVENT_ABNORMAL_MOVEMENT = "abnormal_movement"

    def __init__(
        self,
        immobility_seconds: float = 30.0,
        movement_intensity_threshold: float = 0.7,
        fall_torso_angle_threshold: float = 55.0,
        fall_nose_low_threshold: float = 0.8,
    ):
        self._immobility_seconds = immobility_seconds
        self._movement_threshold = movement_intensity_threshold
        self._fall_torso = fall_torso_angle_threshold
        self._fall_nose_low = fall_nose_low_threshold
        self._last_motion_time: Optional[float] = None
        self._last_hip_y: Optional[float] = None
        self._bed_region_bottom: float = 0.75  # assume bed in lower part of frame

    def process(
        self,
        detections: List[Detection],
        pose: PoseResult,
        motion_metric: float = 0.0,
        timestamp: Optional[float] = None,
    ) -> List[DetectedEvent]:
        """
        Run rule-based event detection.
        motion_metric: 0-1 overall motion (e.g. from frame diff or pose).
        """
        ts = timestamp if timestamp is not None else time.time()
        events: List[DetectedEvent] = []

        person_boxes = [d for d in detections if d.class_name == "person"]
        bed_boxes = [d for d in detections if d.class_name == "bed"]

        # ---- Fall: horizontal posture + low nose (person on ground) ----
        if pose.keypoints and pose.posture == "lying":
            if pose.torso_angle >= self._fall_torso or pose.nose_y_normalized >= self._fall_nose_low:
                conf = min(1.0, (pose.torso_angle / 90.0) * 0.5 + (pose.nose_y_normalized) * 0.5)
                events.append(
                    DetectedEvent(
                        event_type=self.EVENT_FALL,
                        confidence=conf,
                        timestamp=ts,
                        metadata={"posture": pose.posture, "torso_angle": pose.torso_angle},
                    )
                )

        # ---- Bed exit: person bbox center above bed region or no overlap with bed ----
        if person_boxes and bed_boxes:
            for p in person_boxes:
                cx = (p.x1 + p.x2) / 2
                cy = (p.y1 + p.y2) / 2
                # Simple: person center moving above bed region (top of frame)
                if cy < 0.4:  # person in upper half → possible exit
                    events.append(
                        DetectedEvent(
                            event_type=self.EVENT_BED_EXIT,
                            confidence=0.6 + 0.2 * (1.0 - cy),
                            timestamp=ts,
                            metadata={"person_cy": cy},
                        )
                    )
        elif person_boxes and self._last_hip_y is not None:
            # No bed detected: use hip movement upward as proxy for getting up
            if pose.hip_center_y < 0.5 and self._last_hip_y > 0.55:
                events.append(
                    DetectedEvent(
                        event_type=self.EVENT_BED_EXIT,
                        confidence=0.65,
                        timestamp=ts,
                        metadata={"hip_y": pose.hip_center_y},
                    )
                )
        if pose.keypoints:
            self._last_hip_y = pose.hip_center_y

        # ---- Immobility: no significant motion for X seconds ----
        if motion_metric > 0.1 or pose.movement_intensity > 0.1:
            self._last_motion_time = ts
        if self._last_motion_time is not None and (ts - self._last_motion_time) >= self._immobility_seconds:
            events.append(
                DetectedEvent(
                    event_type=self.EVENT_IMMOBILITY,
                    confidence=0.8,
                    timestamp=ts,
                    metadata={"seconds_without_motion": ts - self._last_motion_time},
                )
            )
            self._last_motion_time = None  # reset so we don't spam

        # ---- Abnormal movement: very high movement intensity ----
        if pose.movement_intensity >= self._movement_threshold:
            events.append(
                DetectedEvent(
                    event_type=self.EVENT_ABNORMAL_MOVEMENT,
                    confidence=min(1.0, pose.movement_intensity),
                    timestamp=ts,
                    metadata={"movement_intensity": pose.movement_intensity},
                )
            )

        return events
