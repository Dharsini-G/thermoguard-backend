# 🌡️ ThermoGuard — Heat-Risk Early Warning System

ThermoGuard is a FastAPI-powered backend designed to compute real-time Human Thermal Stress Index (HTSI) and trigger automated emergency hazard alerts for vulnerable wards.

## 🚀 Features
- **Live Heat-Risk Calculation:** Computes WBGT, UTCI, and heat index values.
- **Dynamic Vulnerability Indexing:** Adjusts ward severity based on demographic risk factors.
- **Multi-Channel Alert System:** Integrates with Discord & Twilio for automated emergency broadcasts.
- **RESTful Endpoints:** Serves interactive dashboard data and multi-day hazard forecasts.

## 🛠️ Tech Stack
- **Framework:** FastAPI / Python 3.13
- **Database:** PostgreSQL (Supabase) / SQLAlchemy ORM
- **API Documentation:** Interactive Swagger UI

## ⚙️ Local Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/Dharsini-G/thermoguard-backend.git](https://github.com/Dharsini-G/thermoguard-backend.git)
   cd thermoguard-backend
