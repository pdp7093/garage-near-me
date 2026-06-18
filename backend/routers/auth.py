from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Header
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
import os
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer

import models, schemas
from database import get_db
from utils.file_upload import save_customer_profile_image
import random
import httpx

TWILIO_ACCOUNT_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN    = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
OTP_EXPIRY_MINUTES   = 10

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

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ──────────────────────────────────────────
# ADMIN — ALL CUSTOMERS (paginated)
# GET /api/auth/admin/customers
# ──────────────────────────────────────────

@router.get("/admin/customers")
def admin_get_customers(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):
    from routers.garage_requests import check_admin
    if not x_admin_key:
        raise HTTPException(status_code=401, detail="Admin key required")
    check_admin(x_admin_key)

    from sqlalchemy import or_, func as sqlfunc
    query = db.query(models.Customer)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            models.Customer.name.ilike(like),
            models.Customer.phone.ilike(like),
            models.Customer.email.ilike(like),
        ))

    total = query.count()
    customers = query.order_by(models.Customer.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    rows = []
    for c in customers:
        vehicles = db.query(models.Vehicle).filter(models.Vehicle.customer_id == c.id).all()
        booking_count = db.query(models.Booking).filter(models.Booking.customer_id == c.id).count()
        vehicle_summary = {}
        for v in vehicles:
            vt = (v.vehicle_type or "other").lower()
            vehicle_summary[vt] = vehicle_summary.get(vt, 0) + 1
        vehicle_str = ", ".join(f"{cnt} {vt.capitalize()}" for vt, cnt in vehicle_summary.items()) or "None"
        rows.append({
            "id":            c.id,
            "name":          c.name,
            "phone":         c.phone,
            "email":         c.email,
            "joined_at":     c.created_at.strftime("%b %d, %Y") if c.created_at else "—",
            "vehicle_str":   vehicle_str,
            "booking_count": booking_count,
            "is_active":     True,
        })

    return {
        "total":     total,
        "page":      page,
        "limit":     limit,
        "customers": rows,
    }


# ──────────────────────────────────────────
# SEND OTP — /api/auth/send-otp
# ──────────────────────────────────────────

@router.post("/send-otp")
async def send_otp(
    request: schemas.OTPSendRequest,
    db: Session = Depends(get_db)
):
    """
    Customer apna phone number dalta hai → OTP milta hai.
    Agar phone registered nahi hai toh 404 error.
    """
    # Check karo ki phone registered hai
    customer = db.query(models.Customer).filter(
        models.Customer.phone == request.phone
    ).first()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="No account found with this phone number. Please register first."
        )

    # Purane unused OTPs delete karo
    db.query(models.CustomerOTP).filter(
        models.CustomerOTP.phone == request.phone,
        models.CustomerOTP.is_used == False
    ).delete()

    # Naya OTP generate karo
    otp = str(random.randint(100000, 999999))

    # DB mein save karo
    from datetime import datetime, timedelta
    customer_otp = models.CustomerOTP(
        phone=request.phone,
        otp=otp,
        is_used=False,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )
    db.add(customer_otp)
    db.commit()

    # SMS bhejo
    await send_whatsapp_otp(request.phone, otp)
    print(f"[OTP] Customer {request.phone} → {otp}")

    return {"message": f"OTP sent to {request.phone}"}


# ──────────────────────────────────────────
# VERIFY OTP — /api/auth/verify-otp
# ──────────────────────────────────────────

@router.post("/verify-otp", response_model=schemas.Token)
def verify_otp(
    request: schemas.OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    """
    Customer OTP dalta hai → JWT token milta hai.
    """
    from datetime import datetime
    otp_record = db.query(models.CustomerOTP).filter(
        models.CustomerOTP.phone == request.phone,
        models.CustomerOTP.otp == request.otp,
        models.CustomerOTP.is_used == False,
        models.CustomerOTP.expires_at > datetime.utcnow()
    ).first()

    if not otp_record:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired OTP. Please request a new one."
        )

    customer = db.query(models.Customer).filter(
        models.Customer.phone == request.phone
    ).first()

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # OTP mark as used
    otp_record.is_used = True
    db.commit()

    # JWT token banao
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": customer.phone, "user_id": customer.id, "role": "customer"},
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


# ──────────────────────────────────────────
# SEND OTP FOR REGISTER — /api/auth/send-otp-register
# ──────────────────────────────────────────

@router.post("/send-otp-register")
async def send_otp_register(
    request: schemas.OTPSendRequest,
    db: Session = Depends(get_db)
):
    """
    Register flow: phone pe OTP bhejo.
    Agar phone already registered hai toh error.
    """
    existing = db.query(models.Customer).filter(
        models.Customer.phone == request.phone
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Phone number already registered. Please login instead."
        )

    # Purane unused OTPs delete karo
    db.query(models.CustomerOTP).filter(
        models.CustomerOTP.phone == request.phone,
        models.CustomerOTP.is_used == False
    ).delete()

    otp = str(random.randint(100000, 999999))
    from datetime import datetime, timedelta
    customer_otp = models.CustomerOTP(
        phone=request.phone,
        otp=otp,
        is_used=False,
        expires_at=datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )
    db.add(customer_otp)
    db.commit()

    await send_whatsapp_otp(request.phone, otp)
    print(f"[OTP] Register {request.phone} → {otp}")

    return {"message": f"OTP sent to {request.phone}"}


# ──────────────────────────────────────────
# REGISTER + VERIFY OTP — /api/auth/register-verify
# ──────────────────────────────────────────

@router.post("/register-verify", response_model=schemas.Token)
def register_verify(
    request: schemas.CustomerRegisterVerify,
    db: Session = Depends(get_db)
):
    """
    OTP verify karo + account create karo + token return karo.
    """
    from datetime import datetime
    otp_record = db.query(models.CustomerOTP).filter(
        models.CustomerOTP.phone == request.phone,
        models.CustomerOTP.otp == request.otp,
        models.CustomerOTP.is_used == False,
        models.CustomerOTP.expires_at > datetime.utcnow()
    ).first()

    if not otp_record:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired OTP. Please request a new one."
        )

    # Double check phone not already taken
    existing = db.query(models.Customer).filter(
        models.Customer.phone == request.phone
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered.")

    # Email check
    existing_email = db.query(models.Customer).filter(
        models.Customer.email == request.email
    ).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered.")

    # OTP mark as used
    otp_record.is_used = True

    # Random password generate karo (user kabhi use nahi karega — OTP se login hoga)
    import secrets
    random_password = secrets.token_hex(16)
    hashed_password = get_password_hash(random_password)

    new_customer = models.Customer(
        name=request.name,
        phone=request.phone,
        email=request.email,
        hashed_password=hashed_password
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)

    # Auto login — token banao
    access_token = create_access_token(
        data={"sub": new_customer.phone, "user_id": new_customer.id, "role": "customer"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/register", response_model=schemas.CustomerResponse, status_code=status.HTTP_201_CREATED)
def register_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    # Check if phone exists
    db_user_phone = db.query(models.Customer).filter(models.Customer.phone == customer.phone).first()
    if db_user_phone:
        raise HTTPException(status_code=400, detail="Phone number already registered")
    
    # Check if email exists
    db_user_email = db.query(models.Customer).filter(models.Customer.email == customer.email).first()
    if db_user_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(customer.password)
    new_customer = models.Customer(
        name=customer.name,
        phone=customer.phone,
        email=customer.email,
        hashed_password=hashed_password
    )
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    return new_customer

@router.post("/login", response_model=schemas.Token)
def login(login_data: schemas.LoginRequest, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).filter(models.Customer.phone == login_data.phone).first()
    if not customer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid phone number or password")
    
    if not verify_password(login_data.password, customer.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid phone number or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": customer.phone, "user_id": customer.id, "role": "customer"},
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


# ──────────────────────────────────────────
# GET CURRENT CUSTOMER — /api/auth/me
# ──────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

@router.get("/me", response_model=schemas.CustomerResponse)
def get_me(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Token se apna profile fetch karo.
    Dashboard, sidebar user info ke liye use hoga.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    customer = db.query(models.Customer).filter(models.Customer.id == user_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return customer


# ──────────────────────────────────────────
# SAVE FCM TOKEN — /api/auth/fcm-token
# POST /api/auth/fcm-token
# ──────────────────────────────────────────

@router.post("/fcm-token")
def save_fcm_token(
    token_data: schemas.FCMTokenUpdate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Customer ka FCM token save karo — push notifications ke liye.
    POST /api/auth/fcm-token
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    customer = db.query(models.Customer).filter(models.Customer.id == user_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.fcm_token = token_data.fcm_token
    db.commit()
    return {"message": "FCM token saved"}


# ──────────────────────────────────────────
# UPDATE PROFILE — /api/auth/me
# ──────────────────────────────────────────

@router.patch("/me", response_model=schemas.CustomerResponse)
def update_me(
    name: str = Form(None),
    email: str = Form(None),
    profile_image: UploadFile = File(None),
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Profile update karo — naam, email, ya profile image."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    customer = db.query(models.Customer).filter(models.Customer.id == user_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if name is not None:
        customer.name = name
    if email is not None:
        customer.email = email
    if profile_image is not None:
        # Save the file
        image_path = save_customer_profile_image(profile_image, customer.id, customer.name)
        customer.profile_image = image_path

    db.commit()
    db.refresh(customer)
    return customer