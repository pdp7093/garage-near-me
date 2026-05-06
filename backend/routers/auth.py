from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
import os
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer

import models, schemas
from database import get_db

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
# UPDATE PROFILE — /api/auth/me
# ──────────────────────────────────────────

@router.patch("/me", response_model=schemas.CustomerResponse)
def update_me(
    update_data: schemas.CustomerUpdate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Profile update karo — naam ya email."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    customer = db.query(models.Customer).filter(models.Customer.id == user_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)

    db.commit()
    db.refresh(customer)
    return customer