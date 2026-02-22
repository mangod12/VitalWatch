"""
Alert manager: logs alerts, prints to console, emits WebSocket, optional sound.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional

from ..severity.scoring import SeverityLevel, SeverityResult

logger = logging.getLogger("vitalwatch.alerts")


@dataclass
class AlertPayload:
    event: str
    severity: str
    score: float
    time: float
    details: Optional[dict] = None


class AlertManager:
    """
    Central alerting: log, console, WebSocket broadcast, optional sound.
    """

    def __init__(self, enable_console: bool = True, enable_sound: bool = False):
        self._enable_console = enable_console
        self._enable_sound = enable_sound
        self._ws_broadcast: Optional[Callable[[dict], None]] = None
        self._alerts: List[AlertPayload] = []
        self._max_stored = 100

    def set_ws_broadcast(self, callback: Callable[[dict], None]) -> None:
        """Set a function to broadcast JSON to WebSocket clients."""
        self._ws_broadcast = callback

    def emit(self, severity_result: SeverityResult, event_timestamp: Optional[float] = None) -> None:
        """Emit one alert (log, console, WebSocket, optional sound)."""
        ts = event_timestamp if event_timestamp is not None else time.time()
        payload = AlertPayload(
            event=severity_result.event_type,
            severity=severity_result.severity_level.value,
            score=round(severity_result.severity_score, 3),
            time=ts,
            details=None,
        )
        self._alerts.append(payload)
        if len(self._alerts) > self._max_stored:
            self._alerts = self._alerts[-self._max_stored :]

        msg = f"[{payload.severity}] {payload.event} (score={payload.score}) at {ts}"
        logger.warning(msg)
        if self._enable_console:
            logger.info(msg)

        data = asdict(payload)
        if self._ws_broadcast:
            try:
                self._ws_broadcast(data)
            except Exception as e:
                logger.exception("WebSocket broadcast error: %s", e)

        if self._enable_sound and payload.severity == SeverityLevel.CRITICAL.value:
            self._play_alert_sound()

    def _play_alert_sound(self) -> None:
        """Optional: play system beep or sound file."""
        try:
            import winsound
            winsound.Beep(1000, 300)
        except Exception:
            pass

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Return recent alerts as list of dicts (newest last)."""
        return [asdict(a) for a in self._alerts[-limit:]]
