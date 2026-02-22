"""
Video input system for VitalWatch.
Supports webcam, RTSP, and file sources with a rolling frame buffer.
"""

import cv2
import threading
import time
from collections import deque
from typing import Optional, Tuple


class VideoStream:
    """
    Unified video stream supporting webcam, RTSP, and file input.
    Maintains a rolling buffer of recent frames (default 5-10 seconds).
    """

    def __init__(
        self,
        source: str | int,
        buffer_seconds: float = 7.0,
        max_buffer_frames: int = 210,
    ):
        """
        Args:
            source: Webcam index (int, e.g. 0), RTSP URL (str), or file path (str).
            buffer_seconds: Target buffer duration in seconds (used to cap buffer size).
            max_buffer_frames: Maximum frames to keep in buffer (e.g. 7s @ 30fps ≈ 210).
        """
        self._source = source
        self._cap: Optional[cv2.VideoCapture] = None
        self._buffer: deque = deque(maxlen=max_buffer_frames)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._fps = 30.0
        self._frame_size: Optional[Tuple[int, int]] = None

    def start(self) -> bool:
        """Open the stream and start filling the buffer."""
        if self._running:
            return True
        self._cap = cv2.VideoCapture(self._source)
        if not self._cap.isOpened():
            return False
        self._fps = max(1.0, self._cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        # Allow a few frames to buffer
        time.sleep(0.2)
        return True

    def _read_loop(self) -> None:
        while self._running and self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                break
            if self._frame_size is None:
                self._frame_size = (frame.shape[1], frame.shape[0])
            with self._lock:
                self._buffer.append((time.time(), frame.copy()))
        self._running = False

    def stop(self) -> None:
        """Release the stream and stop the reader thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._buffer.clear()

    def read(self) -> Tuple[bool, Optional[any], float]:
        """
        Get the latest frame from the buffer.
        Returns:
            (success, frame, timestamp)
        """
        with self._lock:
            if not self._buffer:
                return False, None, 0.0
            ts, frame = self._buffer[-1]
            return True, frame.copy(), ts

    def get_buffer(self) -> list:
        """Return a copy of the current buffer (list of (timestamp, frame))."""
        with self._lock:
            return [(t, f.copy()) for t, f in self._buffer]

    def get_fps(self) -> float:
        return self._fps

    def get_frame_size(self) -> Optional[Tuple[int, int]]:
        return self._frame_size

    def is_opened(self) -> bool:
        return self._running and self._cap is not None and self._cap.isOpened()
