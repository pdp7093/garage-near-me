from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os

import models, schemas
from database import get_db
import httpx


MESSAGECENTRAL_CUSTOMER_ID = os.getenv("MESSAGECENTRAL_CUSTOMER_ID", "")
MESSAGECENTRAL_AUTH_TOKEN  = os.getenv("MESSAGECENTRAL_AUTH_TOKEN", "")  # Dashboard > Developer Guide > API Credentials se mila hua Auth Token
MESSAGECENTRAL_BASE_URL    = "https://cpaas.messagecentral.com"

async def send_otp_via_messagecentral(phone: str) -> str:
    """
    Message Central VerifyNow se OTP bhejta hai. Ye khud OTP generate karta hai
    apne system mein (hum apna OTP nahi banate), aur ek verificationId return
    karta hai jo verify karte waqt wapas bhejna hota hai.
    """
    if not MESSAGECENTRAL_CUSTOMER_ID or not MESSAGECENTRAL_AUTH_TOKEN:
        print(f"[OTP] Message Central not configured — cannot send OTP to {phone}")
        return ""
    try:
        to_number = phone.lstrip("+")
        if to_number.startswith("91") and len(to_number) > 10:
            to_number = to_number[2:]

        url = f"{MESSAGECENTRAL_BASE_URL}/verification/v3/send"
        params = {
            "countryCode": "91",
            "flowType": "SMS",
            "mobileNumber": to_number,
            "customerId": MESSAGECENTRAL_CUSTOMER_ID,
            "otpLength": "4",
        }
        headers = {"authToken": MESSAGECENTRAL_AUTH_TOKEN}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, params=params, headers=headers)
            data = resp.json()
            print(f"[OTP] Message Central send response: {resp.status_code} {data}")
            return str(data.get("data", {}).get("verificationId", ""))
    except Exception as e:
        print(f"[OTP] Message Central send error: {e}")
        return ""


async def verify_otp_via_messagecentral(verification_id: str, code: str) -> bool:
    """Message Central se OTP verify karta hai. True/False return karta hai."""
    if not MESSAGECENTRAL_CUSTOMER_ID or not MESSAGECENTRAL_AUTH_TOKEN:
        print(f"[OTP] Message Central not configured — cannot verify OTP")
        return False
    if not verification_id:
        return False
    try:
        url = f"{MESSAGECENTRAL_BASE_URL}/verification/v3/validateOtp"
        params = {
            "verificationId": verification_id,
            "code": code,
        }
        headers = {"authToken": MESSAGECENTRAL_AUTH_TOKEN}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=headers)
            data = resp.json()
            print(f"[OTP] Message Central verify response: {resp.status_code} {data}")
            status_val = data.get("data", {}).get("verificationStatus", "")
            return status_val == "VERIFICATION_COMPLETED"
    except Exception as e:
        print(f"[OTP] Message Central verify error: {e}")
        return False


router = APIRouter()

SECRET_KEY  = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM   = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/garage-auth/verify-otp")

OTP_EXPIRY_MINUTES = 10


# ──────────────────────────────────────────
# HELPER — JWT Token banao
# ──────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ──────────────────────────────────────────
# HELPER — Current garage get karo from token
# ──────────────────────────────────────────

def get_current_garage(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.Garage:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "garage":
            raise HTTPException(status_code=403, detail="Not a garage token")
        garage = db.query(models.Garage).filter(
            models.Garage.id == payload.get("user_id")
        ).first()
        if not garage:
            raise HTTPException(status_code=401, detail="Garage not found")
        return garage
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ──────────────────────────────────────────
# 1. SEND OTP
# POST /api/garage-auth/send-otp
# ──────────────────────────────────────────

@router.post("/send-otp", response_model=schemas.OTPSendResponse)
async def send_otp(
    request: schemas.OTPSendRequest,
    db: Session = Depends(get_db)
):
    garage = db.query(models.Garage).filter(
        models.Garage.phone   == request.phone,
        models.Garage.is_active == True
    ).first()

    if not garage:
        raise HTTPException(
            status_code=404,
            detail="No active garage found with this phone number. Please contact admin."
        )

    verification_id = await send_otp_via_messagecentral(request.phone)
    if not verification_id:
        raise HTTPException(status_code=500, detail="Failed to send OTP. Please try again.")

    print(f"[OTP] Garage {request.phone} → verificationId {verification_id}")

    return {"message": f"OTP sent to {request.phone}", "verification_id": verification_id}


# ──────────────────────────────────────────
# 2. VERIFY OTP → JWT TOKEN
# POST /api/garage-auth/verify-otp
# ──────────────────────────────────────────

@router.post("/verify-otp", response_model=schemas.Token)
async def verify_otp(
    request: schemas.OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    is_valid = await verify_otp_via_messagecentral(request.verification_id, request.otp)

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired OTP. Please request a new one."
        )

    garage = db.query(models.Garage).filter(
        models.Garage.phone    == request.phone,
        models.Garage.is_active == True
    ).first()

    if not garage:
        raise HTTPException(status_code=404, detail="Garage not found")

    token = create_access_token(
        data={
            "sub":     garage.phone,
            "user_id": garage.id,
            "role":    "garage"
        },
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {"access_token": token, "token_type": "bearer"}


# ──────────────────────────────────────────
# 3. GET MY PROFILE
# GET /api/garage-auth/me
# ──────────────────────────────────────────

@router.get("/me", response_model=schemas.GarageResponse)
def get_my_profile(
    current_garage: models.Garage = Depends(get_current_garage),
    db: Session = Depends(get_db)
):
    """
    Token se apna profile fetch karo.
    Dashboard load hote waqt yahi call hoga.

    Billing Logic:
    - Trial period: ₹500 tak free — ₹500 reach hone pe sirf trial complete mark karo, BLOCK NAHI
    - Post-trial: 15th/30th pe billing cycle chalti hai → 48hr grace → phir block
    - Grace period expire hone pe auto-lock
    """

    # ✅ TRIAL PERIOD — ₹500 reach hua to sirf trial complete karo, block nahi
    if not current_garage.has_completed_trial:
        if current_garage.pending_platform_dues and current_garage.pending_platform_dues >= 500.0:
            current_garage.has_completed_trial = True  # ✅ Sirf flag karo
            current_garage.is_credit_locked = False    # ✅ Block bilkul nahi
            db.commit()
            db.refresh(current_garage)

    # ✅ POST-TRIAL — sirf grace period expire hone pe block karo
    elif current_garage.has_completed_trial:
        if current_garage.grace_period_ends_at:
            grace_naive = current_garage.grace_period_ends_at.replace(tzinfo=None)
            if grace_naive < datetime.utcnow():
                if current_garage.pending_platform_dues and current_garage.pending_platform_dues > 0:
                    if not current_garage.is_credit_locked:
                        current_garage.is_credit_locked = True
                        db.commit()
                        db.refresh(current_garage)
                else:
                    # Dues zero ho gaye — unblock karo
                    if current_garage.is_credit_locked:
                        current_garage.is_credit_locked = False
                        current_garage.grace_period_ends_at = None
                        db.commit()
                        db.refresh(current_garage)
            else:
                # Grace period active hai — block nahi hona chahiye
                if current_garage.is_credit_locked:
                    current_garage.is_credit_locked = False
                    db.commit()
                    db.refresh(current_garage)
        else:
            # Post-trial without grace period — block nahi hona chahiye
            if current_garage.is_credit_locked:
                current_garage.is_credit_locked = False
                db.commit()
                db.refresh(current_garage)

    return current_garage



# ──────────────────────────────────────────
# 5. UPDATE MY PROFILE
# PATCH /api/garage-auth/me
# ──────────────────────────────────────────

@router.patch("/me", response_model=schemas.GarageResponse)
def update_my_profile(
    update_data: schemas.GarageUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(current_garage, field, value)

    db.commit()
    db.refresh(current_garage)
    return current_garage


# ──────────────────────────────────────────
# 6. SAVE FCM TOKEN (Push Notifications)
# POST /api/garage-auth/fcm-token
# ──────────────────────────────────────────

@router.post("/fcm-token")
def save_fcm_token(
    payload: schemas.FCMTokenRequest,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    current_garage.fcm_token = payload.fcm_token
    db.commit()
    return {"message": "FCM token saved successfully"}

# ──────────────────────────────────────────
# TEMP TEST — Simple push notification test
# GET /api/garage-auth/test-push
# ──────────────────────────────────────────

@router.get("/test-push")
def test_push(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    from fcm import send_notification
    if not current_garage.fcm_token:
        return {"success": False, "message": "No FCM token saved for this garage"}

    result = send_notification(
        token=current_garage.fcm_token,
        title="🔔 Test Notification",
        body="Ye ek simple test hai — agar ye aaya to push kaam kar raha hai!",
        data={"type": "sos", "screen": "dashboard"}
    )
    return {"success": result}