"""
ThermoGuard — Manual Alert Test
==================================
Sends ONE test WhatsApp alert with realistic "Extreme Danger" numbers,
WITHOUT touching your real weather data or database. Use this purely to
prove to judges/staff that the alert system actually sends real messages.

Run with: python -m app.test_alert
"""

from app.services.alerts import send_whatsapp_alert

if __name__ == "__main__":
    print("Sending test alert...")
    success = send_whatsapp_alert(
        ward_name="Chennai - T.Nagar (DEMO TEST)",
        alert_level="Extreme Danger",
        wbgt_c=34.8,
        risk_score=87.5,
    )
    if success:
        print("✅ Test alert sent successfully — check your WhatsApp now.")
    else:
        print("❌ Alert failed to send — check your .env Twilio credentials.")
