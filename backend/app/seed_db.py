"""
UshnaRaksha — Seed Database
==============================
Populates the wards table with our demo wards + vulnerability data.
Run once after init_db() to get starting data for the API/dashboard.
"""

from app.models.database import SessionLocal, WardDB, init_db
from app.services.ingestion import load_districts_from_csv
from app.services.vulnerability import DEMOGRAPHIC_VULNERABILITY
from geoalchemy2.shape import from_shape
from shapely.geometry import Point


def seed_wards():
    init_db()
    db = SessionLocal()
    try:
        districts = load_districts_from_csv()
        for ward in districts:
            existing = db.query(WardDB).filter(WardDB.ward_id == ward.ward_id).first()
            if existing:
                print(f"Ward {ward.ward_id} already exists, skipping.")
                continue

            vuln = DEMOGRAPHIC_VULNERABILITY.get(ward.ward_id, {})
            point = from_shape(Point(ward.lon, ward.lat), srid=4326)

            db_ward = WardDB(
                ward_id=ward.ward_id,
                ward_name=ward.ward_name,
                city=ward.city,
                lat=ward.lat,
                lon=ward.lon,
                location=point,
                elderly_pct=vuln.get("elderly_pct", 10.0),
                outdoor_worker_pct=vuln.get("outdoor_worker_pct", 20.0),
                slum_housing_pct=vuln.get("slum_housing_pct", 20.0),
                cooling_access_pct=vuln.get("cooling_access_pct", 50.0),
            )
            db.add(db_ward)
            print(f"Added ward: {ward.ward_id} - {ward.ward_name}")

        db.commit()
        print("\nSeeding complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_wards()
