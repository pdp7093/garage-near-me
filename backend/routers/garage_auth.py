from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os
import random

import models, schemas
from database import get_db

router = APIRouter()

SECRET_KEY  = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM   = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/garage-auth/verify-otp")

OTP_EXPIRY_MINUTES = 10  # OTP 10 minute mein expire ho jaayega


# ──────────────────────────────────────────
# HELPER — JWT Token banao
# ──────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
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
def send_otp(
    request: schemas.OTPSendRequest,
    db: Session = Depends(get_db)
):
    """
    Garage owner apna phone number dalta hai → OTP milta hai.
    
    Sirf approved garages ko OTP milega.
    Testing ke liye OTP response mein bhi return hoga.
    Production mein: SMS gateway se send karo (Fast2SMS / Twilio)
    """
    # Check karo ki yeh phone registered garage ka hai
    garage = db.query(models.Garage).filter(
        models.Garage.phone   == request.phone,
        models.Garage.is_active == True
    ).first()

    if not garage:
        raise HTTPException(
            status_code=404,
            detail="No active garage found with this phone number. Please contact admin."
        )

    # Purane unused OTPs delete karo (same phone ke liye)
    db.query(models.GarageOTP).filter(
        models.GarageOTP.phone   == request.phone,
        models.GarageOTP.is_used == False
    ).delete()

    # Naya 6-digit OTP generate karo
    otp = str(random.randint(100000, 999999))

    # Database mein save karo
    garage_otp = models.GarageOTP(
        phone      = request.phone,
        otp        = otp,
        is_used    = False,
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )
    db.add(garage_otp)
    db.commit()

    # TODO: Yahan SMS bhejo — abhi sirf print kar rahe hain
    print(f"\n{'='*40}")
    print(f"OTP for {request.phone}: {otp}")
    print(f"Expires in {OTP_EXPIRY_MINUTES} minutes")
    print(f"{'='*40}\n")

    # Testing ke liye OTP response mein bhi de rahe hain
    # Production mein: return {"message": "OTP sent successfully"}
    return {
        "message": f"OTP sent to {request.phone}",
        "otp": otp  # TESTING ONLY — production mein hataao
    }


# ──────────────────────────────────────────
# 2. VERIFY OTP → JWT TOKEN
# POST /api/garage-auth/verify-otp
# ──────────────────────────────────────────

@router.post("/verify-otp", response_model=schemas.Token)
def verify_otp(
    request: schemas.OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    """
    Garage owner OTP dalta hai → JWT token milta hai.
    Token se phir saare protected endpoints access kar sakta hai.
    """
    # OTP dhundho — phone + otp + unused + not expired
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

    # Garage fetch karo
    garage = db.query(models.Garage).filter(
        models.Garage.phone    == request.phone,
        models.Garage.is_active == True
    ).first()

    if not garage:
        raise HTTPException(status_code=404, detail="Garage not found")

    # OTP mark as used
    otp_record.is_used = True
    db.commit()

    # JWT token banao
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
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Token se apna profile fetch karo.
    Dashboard load hote waqt yahi call hoga.
    """
    return current_garage


# ──────────────────────────────────────────
# 4. UPDATE MY PROFILE
# PATCH /api/garage-auth/me
# ──────────────────────────────────────────

@router.patch("/me", response_model=schemas.GarageResponse)
def update_my_profile(
    update_data: schemas.GarageUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage apna profile update kare — naam, type, SOS toggle etc.
    """
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(current_garage, field, value)

    db.commit()
    db.refresh(current_garage)
    return current_garage