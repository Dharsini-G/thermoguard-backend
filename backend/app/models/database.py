"""
ThermoGuard — Database Models (Supabase Compatible)
===================================================
SQLAlchemy models for storing wards and risk readings in Supabase.
"""

import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL not set. Please set your Supabase connection string in .env."
    )

# Fix connection string if using postgresql:// scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configure SQLAlchemy engine with connection pooling settings for Supabase/PgBouncer
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Automatically reconnects if idle connection drops
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class WardDB(Base):
    __tablename__ = "wards"

    id = Column(Integer, primary_key=True, index=True)
    ward_id = Column(String, unique=True, index=True, nullable=False)
    ward_name = Column(String, nullable=False)
    city = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)

    elderly_pct = Column(Float, default=10.0)
    outdoor_worker_pct = Column(Float, default=20.0)
    slum_housing_pct = Column(Float, default=20.0)
    cooling_access_pct = Column(Float, default=50.0)

    readings = relationship("RiskReadingDB", back_populates="ward")


class RiskReadingDB(Base):
    __tablename__ = "risk_readings"

    id = Column(Integer, primary_key=True, index=True)
    ward_id = Column(String, ForeignKey("wards.ward_id"), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    temp_c = Column(Float)
    rh_pct = Column(Float)
    wind_ms = Column(Float)
    solar_wm2 = Column(Float)

    wbgt_c = Column(Float)
    heat_index_c = Column(Float)
    utci_approx_c = Column(Float)
    vulnerability_index = Column(Float)
    final_risk_score = Column(Float)
    alert_level = Column(String)

    ward = relationship("WardDB", back_populates="readings")


def init_db():
    """Create all tables on Supabase."""
    Base.metadata.create_all(bind=engine)
    print("Database tables created/verified on Supabase successfully.")


def get_db():
    """FastAPI dependency for a DB session per-request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


if __name__ == "__main__":
    init_db()