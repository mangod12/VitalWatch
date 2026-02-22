"""SQLAlchemy ORM models for VitalWatch.
Compatible with both SQLite (local) and PostgreSQL (Docker/production).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, String, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class Event(Base):
    __tablename__ = "events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_id = Column(String, nullable=True)
    event_type = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    severity_score = Column(Float, nullable=False)
    severity_level = Column(String, nullable=False)
    inference_time_ms = Column(Float, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
