"""
ThermoGuard — WhatsApp Alert Module
======================================
Sends automated WhatsApp alerts via Twilio's free Sandbox when a ward's
risk level crosses Danger or Extreme Danger.
"""

import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")  # Twilio sandbox default
ALERT_WHATSAPP_TO = os.getenv("ALERT_WHATSAPP_TO")  # your own number, e.g. whatsapp:+91XXXXXXXXXX
TWILIO_CONTENT_SID = os.getenv("TWILIO_CONTENT_SID")
ALERT_THRESHOLD_LEVELS = {"Danger", "Extreme Danger"}


def send_whatsapp_alert(ward_name: str, alert_level: str, wbgt_c: float, risk_score: float) -> bool:
    """
    Sends a WhatsApp alert for a single ward crossing a risk threshold.
    Returns True if sent successfully, False otherwise (never raises,
    so one failed alert never crashes the main API request).
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not ALERT_WHATSAPP_TO:
        print("[alerts] Twilio credentials not configured — skipping alert.")
        return False

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        message_body = (
            f"THERMOGUARD ALERT\n"
            f"Ward: {ward_name}\n"
            f"Alert Level: {alert_level}\n"
            f"WBGT: {wbgt_c}°C | Risk Score: {risk_score}/100\n"
        )

        if alert_level == "Extreme Danger":
            message_body += "Action: Open cooling centres. Alert hospital ER for surge staffing."
        else:
            message_body += "Action: Restrict outdoor labour 12PM-4PM. Open cooling centres."

        client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=ALERT_WHATSAPP_TO,
            body=message_body,
        )
        print(f"[alerts] WhatsApp alert sent for {ward_name} ({alert_level})")
        return True

    except Exception as e:
        print(f"[alerts] Failed to send alert for {ward_name}: {e}")
        return False


def check_and_send_alerts(ward_results: list) -> int:
    """
    Given a list of ward risk results (from /wards/risk), sends alerts for
    any ward at Danger or Extreme Danger. Returns count of alerts sent.
    """
    sent_count = 0
    for w in ward_results:
        if w["alert_level"] in ALERT_THRESHOLD_LEVELS:
            success = send_whatsapp_alert(
                ward_name=w["ward_name"],
                alert_level=w["alert_level"],
                wbgt_c=w["wbgt_c"],
                risk_score=w["final_risk_score"],
            )
            if success:
                sent_count += 1
    return sent_count
