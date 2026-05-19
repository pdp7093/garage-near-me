"""
SOS Notification System
Broadcasts SOS alerts to nearby garages via FCM and SMS
"""

from typing import List, Dict
import os
import requests
from datetime import datetime

# Firebase Config
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY", "")
FCM_URL = "https://fcm.googleapis.com/fcm/send"

# Twilio Config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
TWILIO_URL = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"


class SOSNotificationService:
    """Service for sending SOS notifications to garages"""
    
    @staticmethod
    def send_fcm_notification(garage_fcm_tokens: List[str], sos_data: Dict):
        """
        Send FCM (Firebase Cloud Messaging) notification to garage mobile apps
        
        garage_fcm_tokens: List of FCM tokens for garage devices
        sos_data: {
            "sos_id": int,
            "sos_number": str,
            "customer_name": str,
            "customer_phone": str,
            "vehicle_type": str,
            "vehicle_number": str,
            "location": {"lat": float, "lng": float},
            "distance_km": float,
            "description": str
        }
        """
        if not FIREBASE_API_KEY or not garage_fcm_tokens:
            print(f"⚠️ FCM: Missing API key or tokens. Skipping...")
            return {"status": "skipped", "reason": "no_credentials"}
        
        results = {"sent": 0, "failed": 0, "details": []}
        
        for token in garage_fcm_tokens:
            try:
                headers = {
                    "Authorization": f"key={FIREBASE_API_KEY}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "to": token,
                    "notification": {
                        "title": f"🆘 SOS Alert - {sos_data['vehicle_type']}",
                        "body": f"{sos_data['customer_name']} - {sos_data['distance_km']}km away",
                        "click_action": "FLUTTER_NOTIFICATION_CLICK",
                        "sound": "default",
                        "priority": "high"
                    },
                    "data": {
                        "sos_id": str(sos_data["sos_id"]),
                        "sos_number": sos_data["sos_number"],
                        "customer_phone": sos_data["customer_phone"],
                        "vehicle_number": sos_data["vehicle_number"],
                        "latitude": str(sos_data["location"]["lat"]),
                        "longitude": str(sos_data["location"]["lng"]),
                        "distance_km": str(sos_data["distance_km"])
                    }
                }
                
                response = requests.post(FCM_URL, json=payload, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    results["sent"] += 1
                    results["details"].append({"token": token[:20] + "...", "status": "sent"})
                    print(f"✅ FCM sent to {token[:20]}...")
                else:
                    results["failed"] += 1
                    results["details"].append({"token": token[:20] + "...", "status": "failed", "error": response.text})
                    print(f"❌ FCM failed for {token[:20]}... - {response.status_code}")
                    
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"token": token[:20] + "...", "status": "error", "error": str(e)})
                print(f"❌ FCM error for {token[:20]}... - {str(e)}")
        
        return results
    
    
    @staticmethod
    def send_sms_notification(garage_phones: List[str], sos_data: Dict, max_sms: int = 3):
        """
        Send SMS via Twilio to top 3 closest garages
        
        garage_phones: List of phone numbers with {phone, distance_km}
        sos_data: SOS information
        max_sms: Max number of SMS to send (top 3 closest)
        """
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            print(f"⚠️ SMS: Twilio credentials missing. Skipping...")
            return {"status": "skipped", "reason": "no_credentials"}
        
        # Sort by distance and take top N
        sorted_phones = sorted(garage_phones, key=lambda x: x["distance_km"])[:max_sms]
        
        results = {"sent": 0, "failed": 0, "details": []}
        
        for garage_phone_data in sorted_phones:
            phone = garage_phone_data["phone"]
            distance = garage_phone_data["distance_km"]
            
            try:
                # Format message
                message = (
                    f"🆘 SOS Alert from {sos_data['customer_name']}\n"
                    f"📍 {distance}km away\n"
                    f"🚗 {sos_data['vehicle_type']} - {sos_data['vehicle_number']}\n"
                    f"📞 {sos_data['customer_phone']}\n"
                    f"SOS ID: {sos_data['sos_number']}"
                )
                
                # Send SMS
                payload = {
                    "From": TWILIO_PHONE_NUMBER,
                    "To": f"+91{phone}",  # Assuming India
                    "Body": message
                }
                
                from requests.auth import HTTPBasicAuth
                response = requests.post(
                    TWILIO_URL,
                    data=payload,
                    auth=HTTPBasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                    timeout=5
                )
                
                if response.status_code in [200, 201]:
                    results["sent"] += 1
                    results["details"].append({"phone": phone[-4:], "status": "sent"})
                    print(f"✅ SMS sent to {phone}")
                else:
                    results["failed"] += 1
                    results["details"].append({"phone": phone[-4:], "status": "failed"})
                    print(f"❌ SMS failed to {phone} - {response.status_code}")
                    
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"phone": phone[-4:], "status": "error"})
                print(f"❌ SMS error to {phone} - {str(e)}")
        
        return results
    
    
    @staticmethod
    def broadcast_sos(db, sos_obj, nearby_garages: List[Dict]):
        """
        Broadcast SOS to all nearby garages
        
        sos_obj: SOS model instance
        nearby_garages: List of nearby garages from get_nearby_garages()
        """
        if not nearby_garages:
            print("⚠️ No nearby garages for broadcast")
            return {"broadcast_result": "no_garages"}
        
        # Prepare SOS data for notifications
        sos_notification_data = {
            "sos_id": sos_obj.id,
            "sos_number": sos_obj.sos_number,
            "customer_name": sos_obj.customer.name if sos_obj.customer else "Unknown",
            "customer_phone": sos_obj.customer.phone if sos_obj.customer else "N/A",
            "vehicle_type": sos_obj.vehicle_type,
            "vehicle_number": sos_obj.vehicle_number or "Unknown",
            "vehicle_model": sos_obj.vehicle_model,
            "location": {"lat": sos_obj.latitude, "lng": sos_obj.longitude},
            "description": sos_obj.description
        }
        
        # Prepare garage data for notifications
        garage_fcm_tokens = []
        garage_sms_data = []
        
        for garage_info in nearby_garages:
            garage_id = garage_info["garage_id"]
            
            # Get garage from DB for device tokens
            import models
            garage = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
            
            if garage:
                # Collect FCM tokens (if stored in DB - need to add this)
                # For now, we'll assume tokens are stored separately
                garage_sms_data.append({
                    "phone": garage.phone,
                    "distance_km": garage_info["distance_km"],
                    "garage_name": garage_info["garage_name"]
                })
                
                # Add to print for debugging
                print(f"📲 Will notify: {garage_info['garage_name']} ({garage.phone})")
        
        broadcast_results = {
            "total_garages": len(nearby_garages),
            "fcm": {"status": "pending"},
            "sms": {"status": "pending"}
        }
        
        # Send FCM (if tokens available)
        if garage_fcm_tokens:
            broadcast_results["fcm"] = SOSNotificationService.send_fcm_notification(
                garage_fcm_tokens,
                {**sos_notification_data, "distance_km": nearby_garages[0].get("distance_km", 0)}
            )
        
        # Send SMS to top 3 closest
        if garage_sms_data:
            broadcast_results["sms"] = SOSNotificationService.send_sms_notification(
                garage_sms_data,
                sos_notification_data,
                max_sms=3
            )
        
        return broadcast_results


# Testing helper
def test_sms_notification():
    """Test SMS sending"""
    test_data = {
        "sos_id": 1,
        "sos_number": "SOS-2026-12345",
        "customer_name": "Raj Kumar",
        "customer_phone": "9876543210",
        "vehicle_type": "four_wheeler",
        "vehicle_number": "GJ-01-AB-1234",
        "vehicle_model": "Honda City",
        "location": {"lat": 23.0225, "lng": 72.5714},
        "description": "Engine not starting"
    }
    
    # This would actually send SMS - test only with valid credentials
    print("Test mode - SMS not sent")
