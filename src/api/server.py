"""
FastAPI backend: MJPEG stream, WebSocket alerts, patient management, health check.
"""

import asyncio
import logging
import queue
from typing import Callable, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

from ..models.patient import PatientDatabase, Patient

logger = logging.getLogger("vitalwatch.api")

# Latest distress detection result (dict)
_latest_distress: dict = {"distress_score": 0.0, "level": "NORMAL", "face_count": 0, "raw_score": 0.0, "faces": []}


class CreatePatientRequest(BaseModel):
    """Request model for creating a new patient."""
    name: str
    department: str
    care_type: str
    gender: Optional[str] = "other"
    assigned_nurse: Optional[str] = None
    bed_number: Optional[str] = None
    notes: Optional[str] = None
    admission_date: Optional[str] = None
    cause: Optional[str] = None
    ward_no: Optional[str] = None
    doctor_assigned: Optional[str] = None
    previous_medical_history: Optional[str] = None


# Frame provider: returns (success, frame_bytes_jpeg, timestamp)
_frame_provider: Optional[Callable[[], tuple]] = None
_ws_connections: list = []
_patient_ws_connections: list = []
_alert_queue: queue.Queue = queue.Queue()
_patient_update_queue: queue.Queue = queue.Queue()
_patient_database: Optional[PatientDatabase] = None


def set_frame_provider(provider: Callable[[], tuple]) -> None:
    global _frame_provider
    _frame_provider = provider


def set_patient_database(db: PatientDatabase) -> None:
    """Set the patient database instance."""
    global _patient_database
    _patient_database = db


def broadcast_alert(data: dict) -> None:
    """Called from sync code (AlertManager); enqueue for async broadcast."""
    _alert_queue.put(data)


def broadcast_patient_update(data: dict) -> None:
    """Called from sync code (main pipeline); enqueue for async broadcast."""
    _patient_update_queue.put(data)


def set_distress_data(data: dict) -> None:
    """Update the latest distress detection result (called from pipeline)."""
    global _latest_distress
    _latest_distress = data


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


async def _patient_update_broadcast_worker() -> None:
    """Drain patient update queue and send to all WebSocket clients."""
    while True:
        try:
            data = _patient_update_queue.get_nowait()
            dead = []
            for ws in _patient_ws_connections:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                if ws in _patient_ws_connections:
                    _patient_ws_connections.remove(ws)
        except queue.Empty:
            pass
        await asyncio.sleep(0.05)


async def _async_broadcast_patient(patient: Patient) -> None:
    """Broadcast new patient to WebSocket clients (async, non-blocking)."""
    try:
        data = {
            "type": "patient_created",
            "patient": patient.to_dict(),
        }
        dead = []
        for ws in _patient_ws_connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in _patient_ws_connections:
                _patient_ws_connections.remove(ws)
    except Exception as e:
        logger.warning(f"Error broadcasting patient update: {e}")


def create_app(static_dir: Optional[str] = None, patient_db: Optional[PatientDatabase] = None) -> FastAPI:
    global _patient_database
    
    app = FastAPI(title="VitalWatch API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if patient_db:
        _patient_database = patient_db

    @app.on_event("startup")
    async def startup():
        asyncio.create_task(_alert_broadcast_worker())
        asyncio.create_task(_patient_update_broadcast_worker())

    # ==================== Health & Status ====================
    @app.get("/api/status")
    @app.get("/status")
    async def status():
        """Health check."""
        return {"status": "ok", "service": "VitalWatch"}

    @app.get("/api/distress")
    async def get_distress():
        """Get the latest distress detection result."""
        return _latest_distress

    @app.get("/api/snapshot")
    async def snapshot():
        """Return the latest frame as a JPEG image (for polling-based feeds)."""
        if _frame_provider:
            ok, frame_bytes, _ = _frame_provider()
            if ok and frame_bytes:
                return Response(content=frame_bytes, media_type="image/jpeg")
        # Return a 1x1 transparent pixel if no frame available
        return Response(status_code=204)

    # ==================== Video Stream ====================
    @app.get("/stream")
    async def stream():
        """MJPEG stream of the live video feed (legacy single patient)."""
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

    # ==================== Patient Management API ====================
    @app.get("/api/patients")
    async def get_patients(department: Optional[str] = None, care_type: Optional[str] = None):
        """
        Get all patients, optionally filtered by department and/or care_type.
        """
        if not _patient_database:
            return JSONResponse({"patients": [], "error": "Patient database not initialized"}, status_code=503)

        patients = _patient_database.get_patients_filtered(department, care_type)
        return {
            "patients": [p.to_dict() for p in patients],
            "count": len(patients),
        }

    @app.get("/api/patient/{patient_id}")
    async def get_patient(patient_id: str):
        """Get a specific patient's details."""
        if not _patient_database:
            return JSONResponse({"error": "Patient database not initialized"}, status_code=503)

        patient = _patient_database.get_patient(patient_id)
        if not patient:
            return JSONResponse({"error": "Patient not found"}, status_code=404)

        return patient.to_dict()

    @app.post("/api/patients/create")
    async def create_patient(request: CreatePatientRequest):
        """Create a new patient with department and care type."""
        if not _patient_database:
            return JSONResponse({"error": "Patient database not initialized"}, status_code=503)

        # Generate unique patient ID
        patient_id = f"P{str(uuid.uuid4().hex[:6]).upper()}"

        # Create new patient
        new_patient = Patient(
            id=patient_id,
            name=request.name,
            department=request.department,
            care_type=request.care_type,
            gender=request.gender or "other",
            assigned_nurse=request.assigned_nurse or "Unassigned",
            bed_number=request.bed_number or "TBD",
            notes=request.notes or "",
            admission_date=request.admission_date,
            cause=request.cause or "",
            ward_no=request.ward_no or "",
            doctor_assigned=request.doctor_assigned,
            previous_medical_history=request.previous_medical_history or "",
        )

        # Add to database
        success = _patient_database.add_patient(new_patient)
        if not success:
            return JSONResponse({"error": "Failed to add patient"}, status_code=400)

        # Return response immediately (no async broadcast - dashboard will reload)
        return {
            "success": True,
            "message": "Patient created successfully",
            "patient": new_patient.to_dict(),
        }

    @app.post("/api/patient/{patient_id}/status")
    async def update_patient_status(patient_id: str, mood_score: float, movement_score: float):
        """Update a patient's mood and movement status."""
        if not _patient_database:
            return JSONResponse({"error": "Patient database not initialized"}, status_code=503)

        patient = _patient_database.update_patient_status(patient_id, mood_score, movement_score)
        if not patient:
            return JSONResponse({"error": "Patient not found"}, status_code=404)

        # Broadcast update to connected clients
        await _async_broadcast_patient(patient)

        return patient.to_dict()

    @app.get("/api/patient/{patient_id}/stream")
    async def patient_stream(patient_id: str):
        """
        MJPEG stream for a specific patient.
        Currently uses the global frame provider.
        Can be extended to support per-patient video sources.
        """
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

    # ==================== WebSocket Connections ====================
    @app.websocket("/alerts")
    async def alerts_websocket(websocket: WebSocket):
        """Legacy alerts WebSocket endpoint."""
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

    @app.websocket("/ws/patients")
    async def patients_websocket(websocket: WebSocket):
        """
        WebSocket for real-time patient updates and alerts.
        Clients can receive:
        - patient_update: when a patient's status changes
        - alert: when an alert is triggered
        - patients_list: initial list of all patients
        """
        await websocket.accept()
        _patient_ws_connections.append(websocket)

        try:
            # Send initial patient list
            if _patient_database:
                patients = _patient_database.get_all_patients()
                await websocket.send_json({
                    "type": "patients_list",
                    "patients": [p.to_dict() for p in patients],
                })

            # Keep connection alive and receive messages
            while True:
                message = await websocket.receive_text()
                # Optional: handle incoming messages from client
                logger.debug(f"Received message from patient WS: {message}")

        except WebSocketDisconnect:
            pass
        finally:
            if websocket in _patient_ws_connections:
                _patient_ws_connections.remove(websocket)

    # ==================== Static Files ====================
    if static_dir:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app

