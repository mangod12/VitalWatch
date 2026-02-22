"""Database session management with retry logic.
Local deployment: defaults to SQLite (no PostgreSQL required).
Docker / production: set DATABASE_URL or POSTGRES_* to use PostgreSQL.
"""
import logging
import os
import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .models import Base

logger = logging.getLogger("vitalwatch.db")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Local deployment: default to SQLite in project directory (no PostgreSQL needed)
    if os.getenv("USE_POSTGRES", "").lower() in ("1", "true", "yes"):
        user = os.getenv("POSTGRES_USER", "admin")
        pwd = os.getenv("POSTGRES_PASSWORD", "password")
        db = os.getenv("POSTGRES_DB", "vitalwatch")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        DATABASE_URL = f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    else:
        db_path = Path(__file__).resolve().parent.parent.parent / "vitalwatch.db"
        DATABASE_URL = f"sqlite:///{db_path}"
        logger.info("Using SQLite for local deployment: %s", db_path)

_engine = None
SessionLocal = None


def get_engine():
    global _engine, SessionLocal
    if _engine is None:
        kwargs = {}
        if DATABASE_URL.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            kwargs["pool_pre_ping"] = False
        else:
            kwargs["pool_pre_ping"] = True
        attempts = 3
        for i in range(attempts):
            try:
                _engine = create_engine(DATABASE_URL, **kwargs)
                SessionLocal = sessionmaker(bind=_engine)
                break
            except OperationalError as e:
                logger.warning("Database connection failed (attempt %s): %s", i + 1, e)
                time.sleep(2)
        if _engine is None:
            raise RuntimeError("Could not create database engine")
    return _engine


def create_tables():
    eng = get_engine()
    Base.metadata.create_all(bind=eng)


def get_session():
    if SessionLocal is None:
        get_engine()
    return SessionLocal()
