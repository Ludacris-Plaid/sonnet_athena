"""
SQLAlchemy engine / session management.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables. Call once at startup / via scripts/init_db.py."""
    # Import models here so they're registered on Base.metadata before create_all
    from app.models import (  # noqa: F401
        property,
        neighborhood,
        comparable,
        client,
        message,
        trust,
        org,
        price_history,
        alert,
        document,
        crm_connection,
        admin_audit,
        calendar_event,
        email_connection,
        conversation,
        platform_setting,
    )

    Base.metadata.create_all(bind=engine)
