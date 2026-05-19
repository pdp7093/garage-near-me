# SOS Broadcasting Configuration

## Overview
SOS alerts are broadcast to all garages within the specified radius using:
1. **FCM (Firebase Cloud Messaging)** - for mobile app notifications
2. **SMS (Twilio)** - for SMS alerts to top 3 closest garages

## Environment Variables Required

Add these to your `.env` file:

```bash
# Firebase Cloud Messaging (FCM)
FIREBASE_API_KEY=your_fcm_server_api_key

# Twilio SMS
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890  # Your Twilio phone number

# Optional: Comma-separated list of test garage phone numbers
TEST_GARAGE_PHONES=9876543210,9876543211
```

## How It Works

### 1. Customer Triggers SOS
```
POST /api/sos/create
{
  "latitude": 23.0225,
  "longitude": 72.5714,
  "address": "Some location",
  "vehicle_type": "four_wheeler",
  "vehicle_number": "GJ-01-AB-1234",
  "vehicle_model": "Honda City",
  "description": "Engine not starting",
  "broadcast_radius_km": 2.0
}
```

### 2. System Finds Nearby Garages
- Searches all active, verified, SOS-available garages
- Filters by 2km radius (or custom radius)
- Sorts by distance

### 3. SOS Created with Status: "broadcasting"
- Record stored in database
- Unique SOS number generated (SOS-2026-XXXXX)

### 4. Notifications Sent
- **FCM**: Push notification to garage mobile apps (requires FCM tokens stored in DB)
- **SMS**: Twilio SMS to top 3 closest garages

### 5. Garage Sees SOS Alert
- Calls `GET /api/sos/active` to see all broadcasting SOS in their radius
- Can accept, decline, or ignore

### 6. Flow Completion
- First garage to accept → status changes to "accepted"
- Mechanic goes on the way → status "on_the_way"
- Reaches location → status "in_progress"
- Work done → status "completed" with final charges

## Testing Broadcasting

### Without Credentials (Dev Mode)
If Firebase/Twilio credentials are missing, the system will:
- Skip notification sending
- Still create SOS record
- Garages can fetch SOS via `GET /api/sos/active`
- Console will show: "⚠️ FCM/SMS: Missing API key"

### With Credentials (Production)
- FCM notifications sent to registered garage devices
- SMS sent to top 3 closest garages
- Success logged to console

## Console Output Example

```
============================================================
🆘 SOS BROADCAST — SOS #1 (SOS-2026-12345)
Customer: Raj Kumar (9876543210)
Location: 23.0225, 72.5714
Vehicle: four_wheeler - GJ-01-AB-1234
Nearby garages: 5
  • Quick Service - 0.5km away
  • Pro Garage - 0.8km away
  • Express Fix - 1.2km away
============================================================

📢 BROADCAST RESULT:
  FCM: {'status': 'skipped', 'reason': 'no_credentials'}
  SMS: {'status': 'skipped', 'reason': 'no_credentials'}
```

## Setup Steps

### Get Firebase Credentials
1. Go to Firebase Console: https://console.firebase.google.com/
2. Select your project
3. Settings → Project Settings → Service Accounts
4. Generate new private key
5. Copy "Server API Key" from Cloud Messaging tab

### Get Twilio Credentials
1. Sign up at https://www.twilio.com/
2. Get Account SID and Auth Token from Dashboard
3. Buy a phone number
4. Use these in `.env`

### Store FCM Tokens
- When garage logs in, mobile app sends FCM device token
- Store in database (need to add `garage_fcm_tokens` table)
- This is for future implementation

## API Response

When SOS is created, response includes:
```json
{
  "id": 1,
  "sos_number": "SOS-2026-12345",
  "customer_id": 5,
  "garage_id": null,
  "latitude": 23.0225,
  "longitude": 72.5714,
  "status": "broadcasting",
  "broadcast_radius_km": 2.0,
  "created_at": "2026-05-19T10:30:00Z",
  "vehicle_type": "four_wheeler",
  "vehicle_number": "GJ-01-AB-1234"
}
```

## Logs to Check

```bash
# Check SOS creation logs
docker logs garage-api  # For Docker
# or tail -f your_log_file

# Should see:
# ✅ FCM sent to 94dfc52...
# ✅ SMS sent to 9876543210
# ❌ FCM failed to... (if error)
```

## Known Limitations

1. **FCM Tokens**: Need to implement device token storage
2. **SMS Cost**: Twilio charges per SMS - budget accordingly
3. **Rate Limiting**: Consider adding rate limits to prevent spam
4. **Broadcast Limit**: Currently broadcasts to all garages in radius - might need pagination for large areas

## Future Enhancements

- [ ] Store FCM device tokens in DB
- [ ] Add broadcast history/logging table
- [ ] Implement SOS acceptance race condition handling (Redis)
- [ ] Add webhook for delivery confirmations
- [ ] SMS delivery reports from Twilio
