"""
Severity scoring for detected events.
Outputs score (0-1) and level: Normal / Warning / Critical.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..events.event_engine import DetectedEvent


class SeverityLevel(str, Enum):
    NORMAL = "Normal"
    WARNING = "Warning"
    CRITICAL = "Critical"


@dataclass
class SeverityResult:
    severity_score: float  # 0-1
    severity_level: SeverityLevel
    event_type: str
    confidence: float


class SeverityScorer:
    """
    Computes severity from event confidence, movement intensity, and duration.
    Formula: score = (event_confidence * 0.6) + (movement_intensity * 0.2) + (duration_factor * 0.2)
    """

    def __init__(
        self,
        warning_threshold: float = 0.4,
        critical_threshold: float = 0.7,
    ):
        self._warning = warning_threshold
        self._critical = critical_threshold

    def score(
        self,
        event: DetectedEvent,
        movement_intensity: float = 0.0,
        duration_seconds: float = 0.0,
    ) -> SeverityResult:
        """
        duration_seconds: how long the event condition has been true (e.g. immobility duration).
        """
        confidence = event.confidence
        # Duration factor: cap at 1.0, e.g. 60s -> 1.0
        duration_factor = min(1.0, duration_seconds / 60.0)
        severity_score = (
            confidence * 0.6
            + movement_intensity * 0.2
            + duration_factor * 0.2
        )
        severity_score = min(1.0, max(0.0, severity_score))

        if severity_score >= self._critical:
            level = SeverityLevel.CRITICAL
        elif severity_score >= self._warning:
            level = SeverityLevel.WARNING
        else:
            level = SeverityLevel.NORMAL

        return SeverityResult(
            severity_score=severity_score,
            severity_level=level,
            event_type=event.event_type,
            confidence=confidence,
        )
