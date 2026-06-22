from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os
import random

import models, schemas
from database import get_db
import httpx


TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

async def send_whatsapp_otp(phone: str, otp: str):
    """Twilio WhatsApp Sandbox se OTP bhejo"""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        print(f"[OTP] Twilio not configured — OTP for {phone}: {otp}")
        return
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        to_number = phone if phone.startswith("+") else f"+{phone}"
        data = {
            "From": TWILIO_WHATSAPP_FROM,
            "To": f"whatsapp:{to_number}",
            "Body": f"Your GarageNearMe OTP is *{otp}*. Valid for 10 minutes. Do not share with anyone."
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                data=data,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            )
            print(f"[OTP] Twilio response: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[OTP] Twilio error: {e}")


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

    db.query(models.GarageOTP).filter(
        models.GarageOTP.phone   == request.phone,
        models.GarageOTP.is_used == False
    ).delete()

    otp = str(random.randint(100000, 999999))

    garage_otp = models.GarageOTP(
        phone      = request.phone,
        otp        = otp,
        is_used    = False,
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )
    db.add(garage_otp)
    db.commit()

    await send_whatsapp_otp(request.phone, otp)
    print(f"[OTP] {request.phone} → {otp}")

    return {"message": f"OTP sent to {request.phone}"}


# ──────────────────────────────────────────
# 2. VERIFY OTP → JWT TOKEN
# POST /api/garage-auth/verify-otp
# ──────────────────────────────────────────

@router.post("/verify-otp", response_model=schemas.Token)
def verify_otp(
    request: schemas.OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    otp_record = db.query(models.GarageOTP).filter(
        models.GarageOTP.phone   == request.phone,
        models.GarageOTP.otp     == request.otp,
        models.GarageOTP.is_used == False,
        models.GarageOTP.expires_at > datetime.utcnow()
    ).first()

    if not otp_record:
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

    otp_record.is_used = True
    db.commit()

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
    elif current_garage.has_completed_trial and current_garage.grace_period_ends_at:
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

    return current_garage


# ──────────────────────────────────────────
# 4. SAVE FCM TOKEN
# POST /api/garage-auth/fcm-token
# ──────────────────────────────────────────

@router.post("/fcm-token")
def save_fcm_token(
    token_data: schemas.FCMTokenUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    current_garage.fcm_token = token_data.fcm_token
    db.commit()
    return {"message": "FCM token saved"}


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
