"""
Patient model and management for VitalWatch dashboard.
Tracks patient information, status, and associated data.
Persists to PostgreSQL via SQLAlchemy.
"""

import os
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional, Dict, List
from enum import Enum

from sqlalchemy import create_engine, Table, Column, MetaData, String, Float, Text, Date, DateTime, inspect
from sqlalchemy.exc import SQLAlchemyError


class PatientStatus(str, Enum):
    """Patient health status levels."""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"


class CareType(str, Enum):
    """Types of care for patients."""
    CCU = "ccu"  # Coronary Care Unit
    ICU = "icu"  # Intensive Care Unit
    GENERAL = "general"  # General Ward


class Department(str, Enum):
    """Hospital departments."""
    CARDIOLOGY = "cardiology"
    NEUROLOGY = "neurology"
    TRAUMA = "trauma"
    GENERAL = "general"
    RESPIRATORY = "respiratory"


class Gender(str, Enum):
    """Patient gender options."""
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


@dataclass
class Patient:
    """
    Patient information for monitoring dashboard.
    """
    id: str
    name: str
    department: str  # Department enum value
    care_type: str  # CareType enum value
    gender: str = "other"  # Gender enum value
    status: str = "normal"  # PatientStatus enum value
    mood_score: float = 0.7  # 0-1, higher = better mood
    movement_score: float = 0.5  # 0-1, higher = more movement
    stream_url: Optional[str] = None
    last_update: Optional[str] = None
    notes: str = ""
    assigned_nurse: Optional[str] = None
    bed_number: Optional[str] = None
    vital_signs: Dict = field(default_factory=dict)
    admission_date: Optional[str] = None  # ISO date string
    cause: str = ""
    ward_no: str = ""
    doctor_assigned: Optional[str] = None
    previous_medical_history: str = ""

    def __post_init__(self):
        if not self.last_update:
            self.last_update = datetime.now().isoformat()
        if not self.admission_date:
            self.admission_date = date.today().isoformat()

    def to_dict(self) -> dict:
        """Convert patient to dictionary."""
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Patient":
        """Create patient from dictionary."""
        # Filter out any keys not in the dataclass to be forward-compatible
        valid_keys = {f.name for f in Patient.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return Patient(**filtered)

    def update_status(self, mood_score: float, movement_score: float):
        """
        Update patient status based on mood and movement scores.

        Args:
            mood_score: 0-1 score for mood (0=sad, 1=happy)
            movement_score: 0-1 score for movement (0=immobile, 1=active)
        """
        self.mood_score = float(mood_score)
        self.movement_score = float(movement_score)
        self.last_update = datetime.now().isoformat()

        # Status logic: critical if mood is very low OR movement is abnormal
        if mood_score < 0.3 or movement_score < 0.15 or movement_score > 0.95:
            self.status = PatientStatus.CRITICAL.value
        elif mood_score < 0.5 or 0.15 <= movement_score < 0.3 or 0.85 < movement_score <= 0.95:
            self.status = PatientStatus.WARNING.value
        else:
            self.status = PatientStatus.NORMAL.value


# --------------- SQLAlchemy table definition ---------------

_metadata = MetaData()

patients_table = Table(
    "patients",
    _metadata,
    Column("id", String(20), primary_key=True),
    Column("name", String(200), nullable=False),
    Column("department", String(50), nullable=False),
    Column("care_type", String(50), nullable=False),
    Column("gender", String(20), nullable=False, server_default="other"),
    Column("status", String(20), nullable=False, server_default="normal"),
    Column("mood_score", Float, nullable=False, server_default="0"),
    Column("movement_score", Float, nullable=False, server_default="0"),
    Column("stream_url", Text, nullable=True),
    Column("last_update", String(50), nullable=True),
    Column("notes", Text, nullable=False, server_default=""),
    Column("assigned_nurse", String(200), nullable=True),
    Column("bed_number", String(50), nullable=True),
    Column("admission_date", String(20), nullable=True),
    Column("cause", Text, nullable=False, server_default=""),
    Column("ward_no", String(50), nullable=False, server_default=""),
    Column("doctor_assigned", String(200), nullable=True),
    Column("previous_medical_history", Text, nullable=False, server_default=""),
)

# Note: vital_signs (dict) is NOT stored in the DB — it is transient runtime data.

_DEFAULT_DB_URL = "postgresql://postgres:ayush0601@localhost:5432/vitalwatch"


class PatientDatabase:
    """Patient database backed by PostgreSQL via SQLAlchemy."""

    def __init__(self, db_url: Optional[str] = None):
        self._logger = logging.getLogger("vitalwatch.patients")
        url = db_url or os.environ.get("DATABASE_URL", _DEFAULT_DB_URL)
        self._logger.info("Connecting to database: %s", url.split("@")[-1])  # log host only
        self._engine = create_engine(url, pool_pre_ping=True)

        # Create table if it doesn't exist
        _metadata.create_all(self._engine)

        # Seed mock data if the table is empty
        if self._count() == 0:
            self._initialize_mock_data()

    # ---- helpers ----

    def _row_to_patient(self, row) -> Patient:
        """Convert a SQLAlchemy Row to a Patient dataclass."""
        d = dict(row._mapping)
        d["vital_signs"] = {}  # not persisted
        return Patient.from_dict(d)

    def _count(self) -> int:
        with self._engine.connect() as conn:
            from sqlalchemy import select, func
            result = conn.execute(select(func.count()).select_from(patients_table))
            return result.scalar() or 0

    # ---- public API (same interface as before) ----

    def get_patient(self, patient_id: str) -> Optional[Patient]:
        """Get a patient by ID."""
        with self._engine.connect() as conn:
            from sqlalchemy import select
            row = conn.execute(
                select(patients_table).where(patients_table.c.id == patient_id)
            ).first()
            return self._row_to_patient(row) if row else None

    def get_all_patients(self) -> List[Patient]:
        """Get all patients."""
        with self._engine.connect() as conn:
            from sqlalchemy import select
            rows = conn.execute(select(patients_table)).fetchall()
            return [self._row_to_patient(r) for r in rows]

    def get_patients_by_department(self, department: str) -> List[Patient]:
        """Get all patients in a specific department."""
        with self._engine.connect() as conn:
            from sqlalchemy import select
            rows = conn.execute(
                select(patients_table).where(patients_table.c.department == department)
            ).fetchall()
            return [self._row_to_patient(r) for r in rows]

    def get_patients_by_care_type(self, care_type: str) -> List[Patient]:
        """Get all patients in a specific care type."""
        with self._engine.connect() as conn:
            from sqlalchemy import select
            rows = conn.execute(
                select(patients_table).where(patients_table.c.care_type == care_type)
            ).fetchall()
            return [self._row_to_patient(r) for r in rows]

    def get_patients_filtered(self, department: Optional[str] = None, care_type: Optional[str] = None) -> List[Patient]:
        """Get patients filtered by department and/or care type."""
        from sqlalchemy import select
        stmt = select(patients_table)
        if department:
            stmt = stmt.where(patients_table.c.department == department)
        if care_type:
            stmt = stmt.where(patients_table.c.care_type == care_type)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).fetchall()
            return [self._row_to_patient(r) for r in rows]

    def add_patient(self, patient: Patient) -> bool:
        """Add a new patient."""
        try:
            d = patient.to_dict()
            d.pop("vital_signs", None)  # not persisted
            with self._engine.begin() as conn:
                conn.execute(patients_table.insert().values(**d))
            return True
        except SQLAlchemyError as e:
            self._logger.error("Failed to add patient %s: %s", patient.id, e)
            return False

    def update_patient(self, patient: Patient) -> bool:
        """Update an existing patient."""
        try:
            d = patient.to_dict()
            d.pop("vital_signs", None)
            pid = d.pop("id")
            with self._engine.begin() as conn:
                result = conn.execute(
                    patients_table.update().where(patients_table.c.id == pid).values(**d)
                )
                return result.rowcount > 0
        except SQLAlchemyError as e:
            self._logger.error("Failed to update patient: %s", e)
            return False

    def remove_patient(self, patient_id: str) -> bool:
        """Remove a patient."""
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    patients_table.delete().where(patients_table.c.id == patient_id)
                )
                return result.rowcount > 0
        except SQLAlchemyError as e:
            self._logger.error("Failed to remove patient %s: %s", patient_id, e)
            return False

    def update_patient_status(self, patient_id: str, mood_score: float, movement_score: float) -> Optional[Patient]:
        """Update a patient's status based on mood and movement scores."""
        patient = self.get_patient(patient_id)
        if not patient:
            return None
        patient.update_status(mood_score, movement_score)
        self.update_patient(patient)
        return patient

    # ---- seeding ----

    def _initialize_mock_data(self):
        """Initialize with sample patient data for demonstration."""
        self._logger.info("Seeding mock patient data into PostgreSQL...")
        mock_patients = [
            Patient(
                id="P001",
                name="John Anderson",
                department=Department.CARDIOLOGY.value,
                care_type=CareType.ICU.value,
                gender=Gender.MALE.value,
                assigned_nurse="Nurse Sarah",
                bed_number="ICU-101",
                ward_no="W-10",
                doctor_assigned="Dr. Smith",
                cause="Post-cardiac surgery monitoring",
                notes="Post-cardiac surgery monitoring",
                previous_medical_history="Hypertension, Diabetes Type 2",
            ),
            Patient(
                id="P002",
                name="Maria Garcia",
                department=Department.CARDIOLOGY.value,
                care_type=CareType.CCU.value,
                gender=Gender.FEMALE.value,
                assigned_nurse="Nurse John",
                bed_number="CCU-05",
                ward_no="W-05",
                doctor_assigned="Dr. Patel",
                cause="Acute coronary syndrome",
                notes="Acute coronary syndrome",
                previous_medical_history="Previous MI in 2022",
            ),
            Patient(
                id="P003",
                name="Robert Chen",
                department=Department.RESPIRATORY.value,
                care_type=CareType.ICU.value,
                gender=Gender.MALE.value,
                assigned_nurse="Nurse Emma",
                bed_number="ICU-102",
                ward_no="W-12",
                doctor_assigned="Dr. Lee",
                cause="Respiratory distress",
                notes="Respiratory distress monitoring",
                previous_medical_history="Chronic asthma",
            ),
            Patient(
                id="P004",
                name="Lisa Thompson",
                department=Department.NEUROLOGY.value,
                care_type=CareType.ICU.value,
                gender=Gender.FEMALE.value,
                assigned_nurse="Nurse Mike",
                bed_number="ICU-103",
                ward_no="W-08",
                doctor_assigned="Dr. Kumar",
                cause="Stroke recovery",
                notes="Stroke recovery observation",
                previous_medical_history="Atrial fibrillation",
            ),
            Patient(
                id="P005",
                name="James Wilson",
                department=Department.TRAUMA.value,
                care_type=CareType.ICU.value,
                gender=Gender.MALE.value,
                assigned_nurse="Nurse Lisa",
                bed_number="ICU-104",
                ward_no="W-15",
                doctor_assigned="Dr. Brown",
                cause="Motor vehicle accident",
                notes="Severe trauma assessment",
                previous_medical_history="None",
            ),
            Patient(
                id="P006",
                name="Patricia Lee",
                department=Department.GENERAL.value,
                care_type=CareType.GENERAL.value,
                gender=Gender.FEMALE.value,
                assigned_nurse="Nurse David",
                bed_number="WARD-201",
                ward_no="W-20",
                doctor_assigned="Dr. Williams",
                cause="General observation",
                notes="General observation",
                previous_medical_history="Hypothyroidism",
            ),
            Patient(
                id="P007",
                name="David Martinez",
                department=Department.CARDIOLOGY.value,
                care_type=CareType.GENERAL.value,
                gender=Gender.MALE.value,
                assigned_nurse="Nurse Sarah",
                bed_number="WARD-202",
                ward_no="W-21",
                doctor_assigned="Dr. Smith",
                cause="Cardiac recovery",
                notes="Cardiac recovery ward",
                previous_medical_history="CABG surgery 2024",
            ),
            Patient(
                id="P008",
                name="Karen White",
                department=Department.RESPIRATORY.value,
                care_type=CareType.GENERAL.value,
                gender=Gender.FEMALE.value,
                assigned_nurse="Nurse John",
                bed_number="WARD-203",
                ward_no="W-22",
                doctor_assigned="Dr. Lee",
                cause="Pneumonia recovery",
                notes="Respiratory recovery",
                previous_medical_history="COPD",
            ),
        ]

        for patient in mock_patients:
            self.add_patient(patient)
        self._logger.info("Seeded %d mock patients.", len(mock_patients))
