from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os

import models, schemas
from database import get_db

router = APIRouter()

# ──────────────────────────────────────────
# PASSWORD & JWT SETUP
# ──────────────────────────────────────────

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/garage/login")

SECRET_KEY             = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM              = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ──────────────────────────────────────────
# GET CURRENT GARAGE (JWT se)
# ──────────────────────────────────────────

def get_current_garage(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.Garage:
    """
    Protected routes ke liye — JWT token se garage nikalta hai.
    Frontend Authorization: Bearer <token> header bhejega.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        garage_id: int = payload.get("user_id")
        role: str = payload.get("role")
        if garage_id is None or role != "garage":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    garage = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if garage is None:
        raise credentials_exception
    return garage


# ──────────────────────────────────────────
# 1. REGISTER
# POST /api/garage/register
# ──────────────────────────────────────────

@router.post("/register", response_model=schemas.GarageResponse, status_code=status.HTTP_201_CREATED)
def register_garage(garage_data: schemas.GarageCreate, db: Session = Depends(get_db)):
    """
    Naya garage register karo.
    Phone aur email unique hona chahiye.
    """
    # Phone check
    if db.query(models.Garage).filter(models.Garage.phone == garage_data.phone).first():
        raise HTTPException(status_code=400, detail="Phone number already registered")

    # Email check (agar diya ho)
    if garage_data.email:
        if db.query(models.Garage).filter(models.Garage.email == garage_data.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")

    # Garage banao
    new_garage = models.Garage(
        name            = garage_data.name,
        owner_name      = garage_data.owner_name,
        phone           = garage_data.phone,
        email           = garage_data.email,
        hashed_password = get_password_hash(garage_data.password),
        garage_type     = garage_data.garage_type,
    )
    db.add(new_garage)
    db.commit()
    db.refresh(new_garage)

    # Default working hours banao (Mon-Sat open, Sun closed)
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in days:
        wh = models.GarageWorkingHours(
            garage_id  = new_garage.id,
            day_of_week = day,
            is_open    = day != "sunday",   # Sunday default band
            open_time  = datetime.strptime("09:00", "%H:%M").time(),
            close_time = datetime.strptime("20:00", "%H:%M").time(),
        )
        db.add(wh)

    # Empty location row banao
    location = models.GarageLocation(garage_id=new_garage.id)
    db.add(location)

    db.commit()
    db.refresh(new_garage)
    return new_garage


# ──────────────────────────────────────────
# 2. LOGIN
# POST /api/garage/login
# ──────────────────────────────────────────

@router.post("/login", response_model=schemas.Token)
def login_garage(login_data: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Phone + password se login karo, JWT token milega.
    """
    garage = db.query(models.Garage).filter(models.Garage.phone == login_data.phone).first()

    if not garage or not verify_password(login_data.password, garage.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password"
        )

    if not garage.is_active:
        raise HTTPException(status_code=403, detail="Your account has been deactivated")

    token = create_access_token(
        data={"sub": garage.phone, "user_id": garage.id, "role": "garage"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": token, "token_type": "bearer"}


# ──────────────────────────────────────────
# 3. GET MY PROFILE
# GET /api/garage/me
# ──────────────────────────────────────────

@router.get("/me", response_model=schemas.GarageResponse)
def get_my_profile(current_garage: models.Garage = Depends(get_current_garage)):
    """
    JWT token se apna poora profile fetch karo.
    Dashboard load hote waqt yahi call hoga.
    """
    return current_garage


# ──────────────────────────────────────────
# 4. UPDATE BASIC INFO
# PATCH /api/garage/me
# ──────────────────────────────────────────

@router.patch("/me", response_model=schemas.GarageResponse)
def update_my_profile(
    update_data: schemas.GarageUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage name, owner name, garage type, logo, SOS toggle update karo.
    Sirf jo fields bheje woh update honge (PATCH).
    """
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(current_garage, field, value)

    db.commit()
    db.refresh(current_garage)
    return current_garage


# ──────────────────────────────────────────
# 5. UPDATE LOCATION
# PATCH /api/garage/me/location
# ──────────────────────────────────────────

@router.patch("/me/location", response_model=schemas.GarageLocationResponse)
def update_location(
    location_data: schemas.GarageLocationCreate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Address & Location tab ka Save Changes.
    GPS (lat/lng) baad mein alag endpoint se update hoga.
    """
    location = db.query(models.GarageLocation).filter(
        models.GarageLocation.garage_id == current_garage.id
    ).first()

    if not location:
        # Pehli baar location save ho rahi hai
        location = models.GarageLocation(garage_id=current_garage.id)
        db.add(location)

    for field, value in location_data.model_dump(exclude_unset=True).items():
        setattr(location, field, value)

    db.commit()
    db.refresh(location)
    return location


# ──────────────────────────────────────────
# 6. UPDATE WORKING HOURS
# PUT /api/garage/me/working-hours
# ──────────────────────────────────────────

@router.put("/me/working-hours", response_model=list[schemas.WorkingHourResponse])
def update_working_hours(
    hours_data: list[schemas.WorkingHourItem],
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Working Hours tab ka Save Changes.
    Saatey din ek saath bhejo — sab update ho jayenge.
    Example body:
    [
      {"day_of_week": "monday", "is_open": true, "open_time": "09:00", "close_time": "20:00"},
      {"day_of_week": "sunday", "is_open": false, "open_time": null, "close_time": null}
    ]
    """
    for hour in hours_data:
        wh = db.query(models.GarageWorkingHours).filter(
            models.GarageWorkingHours.garage_id   == current_garage.id,
            models.GarageWorkingHours.day_of_week == hour.day_of_week
        ).first()

        if wh:
            wh.is_open    = hour.is_open
            wh.open_time  = hour.open_time
            wh.close_time = hour.close_time
        else:
            # Safety: agar row nahi hai toh banao
            db.add(models.GarageWorkingHours(
                garage_id   = current_garage.id,
                day_of_week = hour.day_of_week,
                is_open     = hour.is_open,
                open_time   = hour.open_time,
                close_time  = hour.close_time,
            ))

    db.commit()

    return db.query(models.GarageWorkingHours).filter(
        models.GarageWorkingHours.garage_id == current_garage.id
    ).all()


# ──────────────────────────────────────────
# 7. UPDATE BANKING
# PATCH /api/garage/me/banking
# ──────────────────────────────────────────

@router.patch("/me/banking", response_model=schemas.GarageBankingResponse)
def update_banking(
    banking_data: schemas.GarageBankingCreate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Banking & Payouts tab ka Save Changes.
    """
    banking = db.query(models.GarageBanking).filter(
        models.GarageBanking.garage_id == current_garage.id
    ).first()

    if not banking:
        banking = models.GarageBanking(garage_id=current_garage.id)
        db.add(banking)

    for field, value in banking_data.model_dump(exclude_unset=True).items():
        setattr(banking, field, value)

    db.commit()
    db.refresh(banking)
    return banking


# ──────────────────────────────────────────
# 8. ADD SERVICE
# POST /api/garage/me/services
# ──────────────────────────────────────────

@router.post("/me/services", response_model=schemas.GarageServiceResponse, status_code=201)
def add_service(
    service_data: schemas.GarageServiceCreate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Services tab — naya service add karo.
    """
    service = models.GarageService(
        garage_id    = current_garage.id,
        service_name = service_data.service_name,
        price        = service_data.price,
        is_available = service_data.is_available,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


# ──────────────────────────────────────────
# 9. DELETE SERVICE
# DELETE /api/garage/me/services/{service_id}
# ──────────────────────────────────────────

@router.delete("/me/services/{service_id}", status_code=204)
def delete_service(
    service_id: int,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Service remove karo.
    """
    service = db.query(models.GarageService).filter(
        models.GarageService.id        == service_id,
        models.GarageService.garage_id == current_garage.id
    ).first()

    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    db.delete(service)
    db.commit()
    return None