"""
VitalWatch main pipeline: video -> detection + pose -> events -> severity -> alerts.
Runs processing loop and optionally starts FastAPI + dashboard.
"""

import argparse
import logging
import threading
import time
import signal
from pathlib import Path
import yaml

import cv2

from .video import VideoStream
from .models import ObjectDetector, PoseEstimator
from .events import EventEngine
from .severity import SeverityScorer
from .alerts import AlertManager
from .api.server import create_app, set_frame_provider, broadcast_alert
from .db import session as db_session, models as db_models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vitalwatch")

# Latest frame as JPEG bytes for MJPEG stream
_latest_jpeg: list = [None]  # list to allow mutability in nested scope
_latest_severity: list = [{"level": "Normal", "score": 0.0}]


def _frame_provider():
    ok = _latest_jpeg[0] is not None
    return ok, _latest_jpeg[0] or b"", time.time()


def run_pipeline(
    source: str | int,
    no_server: bool = False,
    port: int = 8000,
    model_path: str = "yolov8n.pt",
) -> None:
    # load configuration file
    cfg_path = Path("config.yaml")
    config = {}
    if cfg_path.is_file():
        with open(cfg_path, "r") as f:
            config = yaml.safe_load(f) or {}
    else:
        logger.warning("config.yaml not found; using defaults")

    # database setup
    db_session.get_engine()
    db_session.create_tables()

    stream = VideoStream(source=source, buffer_seconds=7.0)
    if not stream.start():
        raise RuntimeError("Could not open video source")

    detector = ObjectDetector(model_path=model_path)
    pose_est = PoseEstimator()
    event_engine = EventEngine(
        immobility_seconds=config.get("immobility_seconds", 30.0),
        movement_intensity_threshold=config.get("movement_intensity_threshold", 0.7),
        fall_torso_angle_threshold=config.get("fall_torso_angle_threshold", 55.0),
        fall_nose_low_threshold=config.get("fall_nose_low_threshold", 0.8),
    )
    severity_scorer = SeverityScorer(
        warning_threshold=config.get("warning_threshold", 0.4), 
        critical_threshold=config.get("critical_threshold", 0.7),
    )
    alert_manager = AlertManager(enable_console=True, enable_sound=False)
    alert_manager.set_ws_broadcast(broadcast_alert)

    # track last firing times to enforce cooldown
    cooldown = config.get("event_cooldown_seconds", 30.0)
    last_fired: dict[str, float] = {}

    # setup graceful shutdown
    should_stop = False
    def _handle_sig(signum, frame):
        nonlocal should_stop
        logger.info("received signal %s, stopping", signum)
        should_stop = True
    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    set_frame_provider(_frame_provider)

    if not no_server:
        import uvicorn
        static_dir = Path(__file__).parent.parent / "dashboard"
        app = create_app(static_dir=str(static_dir) if static_dir.is_dir() else None)
        server_thread = threading.Thread(
            target=lambda: uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning"),
            daemon=True,
        )
        server_thread.start()
        logger.info("Dashboard and API at http://localhost:%s", port)

    try:
        while stream.is_opened() and not should_stop:
            ret, frame, ts = stream.read()
            if not ret or frame is None:
                time.sleep(0.05)
                continue

            start_inf = time.time()
            detections = detector.run(frame)
            pose = pose_est.run(frame)

            motion = pose.movement_intensity
            events = event_engine.process(detections, pose, motion_metric=motion, timestamp=ts)

            current_level = "Normal"
            current_score = 0.0
            for ev in events:
                # cooldown check
                last = last_fired.get(ev.event_type, 0)
                if ts - last < cooldown:
                    continue
                last_fired[ev.event_type] = ts

                duration = ev.metadata.get("seconds_without_motion", 0) or 0
                res = severity_scorer.score(ev, movement_intensity=motion, duration_seconds=duration)
                if res.severity_level.value != "Normal":
                    current_level = res.severity_level.value
                    current_score = res.severity_score
                    alert_manager.emit(res, event_timestamp=ev.timestamp)

                # persist to database
                inf_time = (time.time() - start_inf) * 1000.0
                sess = None
                try:
                    sess = db_session.get_session()
                    e = db_models.Event(
                        source_id=str(source),
                        event_type=ev.event_type,
                        confidence=ev.confidence,
                        severity_score=res.severity_score,
                        severity_level=res.severity_level.value,
                        inference_time_ms=inf_time,
                        model_version=config.get("model_version", "v1.0"),
                    )
                    sess.add(e)
                    sess.commit()
                except Exception as db_err:
                    logger.exception("failed to write event to db: %s", db_err)
                finally:
                    if sess is not None:
                        sess.close()

            _latest_severity[0] = {"level": current_level, "score": current_score}

            # Draw overlays
            for d in detections:
                color = (0, 255, 0) if d.class_name == "person" else (255, 165, 0)
                cv2.rectangle(frame, (d.x1, d.y1), (d.x2, d.y2), color, 2)
                cv2.putText(frame, f"{d.class_name} {d.confidence:.2f}", (d.x1, d.y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            # Severity banner
            color = (0, 255, 0) if current_level == "Normal" else (0, 255, 255) if current_level == "Warning" else (0, 0, 255)
            cv2.rectangle(frame, (0, 0), (frame.shape[1], 28), color, -1)
            cv2.putText(frame, f"Severity: {current_level} ({current_score:.2f})", (10, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

            _, jpeg = cv2.imencode(".jpg", frame)
            _latest_jpeg[0] = jpeg.tobytes()

            if no_server:
                cv2.imshow("VitalWatch", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        stream.stop()
        pose_est.close()
        cv2.destroyAllWindows()
        # dispose engine
        try:
            db_session.get_engine().dispose()
        except Exception:
            pass
        logger.info("Pipeline stopped.")


def main() -> None:
    p = argparse.ArgumentParser(description="VitalWatch – real-time patient event detection")
    p.add_argument("source", nargs="?", default="0", help="Webcam index (0), RTSP URL, or file path")
    p.add_argument("--no-server", action="store_true", help="Disable web dashboard and API")
    p.add_argument("--port", type=int, default=8000, help="API/dashboard port")
    p.add_argument("--model", default="yolov8n.pt", help="YOLOv8 model path")
    args = p.parse_args()
    source = int(args.source) if args.source.isdigit() else args.source
    run_pipeline(source=source, no_server=args.no_server, port=args.port, model_path=args.model)


if __name__ == "__main__":
    main()
