"""
GarageNearMe — FCM Notification Helper
Firebase Admin SDK (new project: garagenearme-b5e36)
"""
import os, logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    _SA = os.path.join(os.path.dirname(__file__), "..", "firebase-service-account.json")
    if not firebase_admin._apps:
        cred = credentials.Certificate(_SA)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized ✅")
    FCM_AVAILABLE = True
except Exception as e:
    logger.warning(f"Firebase init failed: {e}")
    FCM_AVAILABLE = False


def send_notification(token: str, title: str, body: str, data: Optional[dict] = None) -> bool:
    if not FCM_AVAILABLE or not token:
        return False
    try:
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={str(k): str(v) for k, v in (data or {}).items()},
            token=token,
            android=messaging.AndroidConfig(priority="high"),
            webpush=messaging.WebpushConfig(
                headers={"Urgency": "high"},
                notification=messaging.WebpushNotification(title=title, body=body, icon="/assets/icon-192.png")
            )
        )
        messaging.send(msg)
        logger.info(f"Notification sent ✅ — {title}")
        return True
    except Exception as e:
        logger.error(f"Send failed: {e}")
        return False


def send_to_multiple(tokens: list, title: str, body: str, data: Optional[dict] = None) -> int:
    return sum(1 for t in tokens if send_notification(t, title, body, data))


class GarageNotifications:
    @staticmethod
    def new_booking(token, booking_id, customer_name, service):
        return send_notification(token, "🔧 Nayi Booking!", f"{customer_name} ne {service} ke liye booking ki hai.", {"type": "new_booking", "booking_id": str(booking_id), "screen": "bookings"})

    @staticmethod
    def new_sos(token, sos_id, vehicle_type, distance_km):
        dist = f"{distance_km:.1f}km" if distance_km else "nearby"
        return send_notification(token, "🚨 SOS Emergency Alert!", f"{vehicle_type} road pe phansa — {dist} door. Pehle accept karo!", {"type": "sos", "sos_id": str(sos_id), "screen": "sos-alerts"})

    @staticmethod
    def booking_cancelled(token, booking_id):
        return send_notification(token, "❌ Booking Cancel Ho Gayi", f"Booking #GNM-{booking_id} customer ne cancel kar di.", {"type": "booking_cancelled", "booking_id": str(booking_id), "screen": "bookings"})


class CustomerNotifications:
    @staticmethod
    def booking_accepted(token, booking_id, garage_name):
        return send_notification(token, "✅ Booking Accept Ho Gayi!", f"{garage_name} ne aapki booking accept kar li.", {"type": "booking_accepted", "booking_id": str(booking_id), "screen": f"booking-detail/{booking_id}"})

    @staticmethod
    def mechanic_on_way(token, booking_id, garage_name):
        return send_notification(token, "🚗 Mechanic Aa Raha Hai!", f"{garage_name} aapke location pe aa raha hai.", {"type": "mechanic_on_way", "booking_id": str(booking_id), "screen": f"booking-detail/{booking_id}"})

    @staticmethod
    def estimate_ready(token, booking_id, amount):
        return send_notification(token, "💰 Estimate Ready Hai!", f"Aapki gaadi ka estimate ₹{amount:.0f} hai.", {"type": "estimate_ready", "booking_id": str(booking_id), "screen": f"booking-detail/{booking_id}"})

    @staticmethod
    def repair_complete(token, booking_id, garage_name):
        return send_notification(token, "🎉 Repair Complete!", f"{garage_name} ne aapki gaadi theek kar di.", {"type": "repair_complete", "booking_id": str(booking_id), "screen": f"booking-detail/{booking_id}"})

    @staticmethod
    def sos_accepted(token, sos_id, garage_name):
        return send_notification(token, "✅ Help Aa Rahi Hai!", f"{garage_name} aapki SOS accept karke aa raha hai!", {"type": "sos_accepted", "sos_id": str(sos_id), "screen": f"sos-tracking/{sos_id}"})