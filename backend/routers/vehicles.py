from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import os

import models
from database import get_db

router = APIRouter()

SECRET_KEY    = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM     = os.getenv("ALGORITHM", "HS256")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ──────────────────────────────────────────
# SCHEMAS (inline — simple enough)
# ──────────────────────────────────────────

class VehicleCreate(BaseModel):
    vehicle_type:   str             # four_wheeler | two_wheeler
    vehicle_number: str             # "GJ01AB1234"
    description:    Optional[str] = None   # "Red Swift Dzire"

class VehicleResponse(BaseModel):
    id:             int
    vehicle_type:   str
    vehicle_number: str
    description:    Optional[str] = None
    created_at:     datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# AUTH HELPER
# ──────────────────────────────────────────

def get_current_customer(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.Customer:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "customer":
            raise HTTPException(status_code=403, detail="Not a customer token")
        customer = db.query(models.Customer).filter(
            models.Customer.id == payload.get("user_id")
        ).first()
        if not customer:
            raise HTTPException(status_code=401, detail="Customer not found")
        return customer
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ──────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────

@router.get("/", response_model=list[VehicleResponse])
def get_my_vehicles(
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """Apni saari vehicles dekho. GET /api/vehicles/"""
    return db.query(models.Vehicle).filter(
        models.Vehicle.customer_id == current_customer.id
    ).order_by(models.Vehicle.created_at.desc()).all()


@router.post("/", response_model=VehicleResponse, status_code=201)
def add_vehicle(
    vehicle_data: VehicleCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """Naya vehicle add karo. POST /api/vehicles/"""
    # Duplicate number check
    existing = db.query(models.Vehicle).filter(
        models.Vehicle.customer_id    == current_customer.id,
        models.Vehicle.vehicle_number == vehicle_data.vehicle_number.upper()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Vehicle with this number already added")

    vehicle = models.Vehicle(
        customer_id    = current_customer.id,
        vehicle_type   = vehicle_data.vehicle_type,
        vehicle_number = vehicle_data.vehicle_number.upper(),
        description    = vehicle_data.description,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """Vehicle delete karo. DELETE /api/vehicles/{vehicle_id}"""
    vehicle = db.query(models.Vehicle).filter(
        models.Vehicle.id          == vehicle_id,
        models.Vehicle.customer_id == current_customer.id
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    db.delete(vehicle)
    db.commit()
    return None