"""
FastAPI backend: MJPEG stream, WebSocket alerts, health check.
"""

import asyncio
import logging
import queue
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from ..db import session as db_session, models as db_models
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("vitalwatch.api")

# Frame provider: returns (success, frame_bytes_jpeg, timestamp)
_frame_provider: Optional[Callable[[], tuple]] = None
_ws_connections: list = []
_alert_queue: queue.Queue = queue.Queue()


def set_frame_provider(provider: Callable[[], tuple]) -> None:
    global _frame_provider
    _frame_provider = provider


def broadcast_alert(data: dict) -> None:
    """Called from sync code (AlertManager); enqueue for async broadcast."""
    _alert_queue.put(data)


async def _alert_broadcast_worker() -> None:
    """Drain alert queue and send to all WebSocket clients."""
    while True:
        try:
            data = _alert_queue.get_nowait()
            dead = []
            for ws in _ws_connections:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in _ws_connections:
                    _ws_connections.remove(ws)
        except queue.Empty:
            pass
        await asyncio.sleep(0.05)


def create_app(static_dir: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="VitalWatch API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    async def startup():
        asyncio.create_task(_alert_broadcast_worker())

    @app.get("/health")
    async def health():
        """Health check."""
        return {"status": "ok", "service": "VitalWatch"}

    @app.get("/events")
    async def list_events():
        """Return last 50 events from database."""
        sess = db_session.get_session()
        try:
            rows = (
                sess.query(db_models.Event)
                .order_by(db_models.Event.created_at.desc())
                .limit(50)
                .all()
            )
            result = [
                {
                    "event_type": r.event_type,
                    "confidence": r.confidence,
                    "severity_score": r.severity_score,
                    "severity_level": r.severity_level,
                    "inference_time_ms": r.inference_time_ms,
                    "model_version": r.model_version,
                    "created_at": r.created_at.isoformat(),
                    "source_id": r.source_id,
                }
                for r in rows
            ]
            return result
        finally:
            sess.close()

    @app.get("/stream")
    async def stream():
        """MJPEG stream of the live video feed."""
        async def generate():
            while True:
                if _frame_provider:
                    ok, frame_bytes, _ = _frame_provider()
                    if ok and frame_bytes is not None:
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n")
                await asyncio.sleep(0.033)

        return StreamingResponse(
            generate(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.websocket("/alerts")
    async def alerts_websocket(websocket: WebSocket):
        await websocket.accept()
        _ws_connections.append(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            if websocket in _ws_connections:
                _ws_connections.remove(websocket)

    if static_dir:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
