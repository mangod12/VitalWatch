# VitalWatch

**Real-time patient event detection system using computer vision.**

VitalWatch accepts webcam or RTSP video streams, detects basic patient events (fall, bed-exit, abnormal movement, immobility), assigns severity scores, triggers structured alerts, and provides a simple live dashboard.

---

## Architecture (text diagram)

```
                    +------------------+
                    |  Video Source    |
                    | (Webcam / RTSP)  |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |   VideoStream    |  (rolling buffer)
                    +--------+---------+
                             |
         +-------------------+-------------------+
         v                   v                   v
+----------------+  +----------------+  +----------------+
| ObjectDetector |  | PoseEstimator  |  | Motion metrics |
|   (YOLOv8)     |  | (MediaPipe)   |  | (from pose)    |
+--------+-------+  +--------+-------+  +--------+-------+
         |                   |                   |
         +-------------------+-------------------+
                             |
                             v
                    +------------------+
                    |   EventEngine    |  (rule-based)
                    | fall, bed_exit,  |
                    | immobility,      |
                    | abnormal_movement|
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  SeverityScorer  |  (0–1 score,
                    | Normal/Warning/  |   level)
                    | Critical         |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  AlertManager    |  log, console,
                    |  WebSocket       |  optional sound
                    +--------+---------+
                             |
         +-------------------+-------------------+
         v                   v                   v
   [ Console ]         [ WebSocket ]        [ Dashboard ]
                            |
                    +-------+-------+
                    |  FastAPI      |
                    | /stream       |
                    | /alerts (WS)  |
                    | /status      |
                    +--------------+
```

---

## Project layout

```
/src
  /video       stream.py          # VideoStream (webcam, RTSP, buffer)
  /models      detector.py       # YOLOv8 object detection
                pose.py          # MediaPipe pose
  /events      event_engine.py   # Rule-based event detection
  /severity    scoring.py       # Severity score and level
  /alerts      alert_manager.py # Log, console, WebSocket
  /api         server.py        # FastAPI + MJPEG + WebSocket
  main.py                        # Pipeline entrypoint
/dashboard     index.html        # Simple live dashboard
requirements.txt
README.md
```

---

## Installation

1. **Clone or open the project**

   ```bash
   cd TeleICU-Monitoring-System-main
   ```

2. **Create a virtual environment (recommended)**

   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   # source venv/bin/activate  # macOS/Linux
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

   On first run, YOLOv8 will download a pretrained weights file (e.g. `yolov8n.pt`) if not present.

---

## How to run

**With dashboard (default):**

```bash
python -m src.main 0
```

- `0` = default webcam. Use another index for a different camera.
- Open **http://localhost:8000** for the dashboard (live feed, severity, alerts, event log).

**RTSP stream:**

```bash
python -m src.main "rtsp://user:pass@host/path"
```

**Video file:**

```bash
python -m src.main path/to/video.mp4
```

**Without web server (OpenCV window only):**

```bash
python -m src.main 0 --no-server
```

**Options:**

- `--port 8000` – API/dashboard port (default 8000).
- `--model yolov8n.pt` – YOLOv8 model (default: pretrained nano).
- `--no-server` – Disable FastAPI and dashboard; show only OpenCV window.

---

## Supported inputs

| Input        | Example                    |
|-------------|----------------------------|
| Webcam      | `0`, `1`                   |
| RTSP        | `rtsp://host/path`         |
| Local file  | `path/to/video.mp4`        |

---

## Event types (MVP)

- **Fall** – Horizontal posture (torso angle / low nose) from pose.
- **Bed exit** – Person in upper frame or hip moving up (no bed model required).
- **Immobility** – No significant motion for a configured duration (e.g. 30 s).
- **Abnormal movement** – High movement intensity from pose.

Severity is computed from event confidence, movement intensity, and duration. Alerts are logged, printed to console, and pushed over WebSocket to the dashboard.

---

## Dashboard

- **Live video feed** – MJPEG from `/stream`.
- **Severity indicator** – Green (Normal), Yellow (Warning), Red (Critical).
- **Active alerts panel** – Latest alerts from WebSocket.
- **Event log** – Timestamps and event types.

---

## Future roadmap

- Optional bed detection (custom or pretrained model).
- Configurable thresholds via config file or env.
- Optional recording of alert clips.
- Integration with hospital or monitoring systems (APIs, webhooks).
- Tuning and validation on real ICU/patient datasets.

---

## License

See `LICENSE` in the repository. This project is provided as-is for monitoring and research use.
