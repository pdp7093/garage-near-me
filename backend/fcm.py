"""
GarageNearMe — FCM Notification Helper
Firebase Admin SDK
"""
import os, logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    _SA = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")
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
        full_data = {
            "title": title,
            "body": body,
            **{str(k): str(v) for k, v in (data or {}).items()}
        }
        is_sos = (data or {}).get("type") in ("sos", "sos_alert")

        import uuid
        android_notification_kwargs = {
            "title": title,
            "body": body,
            "icon": "@mipmap/ic_launcher",
            "sound": "notification",
            "tag": str(uuid.uuid4()) # Forcing a unique tag so it rings every time and doesn't silently group
        }
        if is_sos:
            android_notification_kwargs["channel_id"] = "sos_alerts_loud"
        elif (data or {}).get("type") in ("new_booking", "booking_accepted", "estimate_ready", "mechanic_on_way", "repair_complete", "booking_cancelled"):
            android_notification_kwargs["channel_id"] = "booking_alerts"

        msg = messaging.Message(
            # Top-level notification — Android OS khud tray mein dikhata hai,
            # chahe app killed ho, background ho, ya foreground ho.
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=full_data,
            token=token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(**android_notification_kwargs)
            ),
        )
        response = messaging.send(msg)
        logger.info(f"Notification sent ✅ — {title} — response: {response}")
        print(f"✅ FCM sent — {title} — message_id: {response}")
        return True
    except Exception as e:
        logger.error(f"Send failed: {e}")
        print(f"⚠️ FCM send failed: {e}")
        return False


def send_to_multiple(tokens: list, title: str, body: str, data: Optional[dict] = None) -> int:
    return sum(1 for t in tokens if send_notification(t, title, body, data))

class GarageNotifications:
    @staticmethod
    def new_booking(token, booking_id, customer_name, service):
        return send_notification(
            token,
            "🔧 Nayi Booking!",
            f"{customer_name} ne {service} ke liye booking ki hai.",
            {"type": "new_booking", "booking_id": str(booking_id), "screen": "bookings"}
        )