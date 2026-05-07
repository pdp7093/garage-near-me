from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os
import random
import string

import models, schemas
from database import get_db

router = APIRouter()

# ──────────────────────────────────────────
# ADMIN AUTH (Simple secret key check)
# Production mein proper admin auth banayenge
# ──────────────────────────────────────────

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026")

def verify_admin(x_admin_key: str = None):
    """
    Abhi simple secret key se admin verify karenge.
    Header mein: X-Admin-Key: gnm_admin_secret_2026
    """
    from fastapi import Header
    return x_admin_key

# Simple admin check function
def check_admin(x_admin_key: str):
    if x_admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin key")


# ──────────────────────────────────────────
# 1. GARAGE REQUEST SUBMIT (Public)
# POST /api/garage-requests/
# ──────────────────────────────────────────

@router.post("/", response_model=schemas.GarageRequestResponse, status_code=201)
def submit_garage_request(
    request_data: schemas.GarageRequestCreate,
    db: Session = Depends(get_db)
):
    """
    Garage owner onboarding form bharta hai.
    Koi bhi submit kar sakta hai — no auth required.
    Admin baad mein review karega.
    """
    # Same phone se duplicate request check
    existing = db.query(models.GarageRequest).filter(
        models.GarageRequest.phone  == request_data.phone,
        models.GarageRequest.status == models.GarageRequestStatus.pending
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A request with this phone number is already pending review."
        )

    # Agar already approved garage hai
    garage_exists = db.query(models.Garage).filter(
        models.Garage.phone == request_data.phone
    ).first()
    if garage_exists:
        raise HTTPException(
            status_code=400,
            detail="A garage with this phone number is already registered."
        )

    new_request = models.GarageRequest(
        owner_name  = request_data.owner_name,
        garage_name = request_data.garage_name,
        phone       = request_data.phone,
        email       = request_data.email,
        garage_type = request_data.garage_type,
        address     = request_data.address,
        city        = request_data.city,
        pincode     = request_data.pincode,
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
    return new_request


# ──────────────────────────────────────────
# 2. GET ALL REQUESTS (Admin)
# GET /api/garage-requests/admin/all
# ──────────────────────────────────────────

@router.get("/admin/all", response_model=list[schemas.GarageRequestResponse])
def get_all_requests(
    status: str = "pending",   # ?status=pending / approved / rejected
    db: Session = Depends(get_db),
    x_admin_key: str = None
):
    """
    Admin saari requests dekhe.
    GET /api/garage-requests/admin/all?status=pending
    Header: X-Admin-Key: gnm_admin_secret_2026
    """
    from fastapi import Header
    check_admin(x_admin_key)

    query = db.query(models.GarageRequest)
    if status:
        try:
            status_enum = models.GarageRequestStatus(status)
            query = query.filter(models.GarageRequest.status == status_enum)
        except ValueError:
            pass

    return query.order_by(models.GarageRequest.created_at.desc()).all()


# ──────────────────────────────────────────
# 3. APPROVE REQUEST (Admin)
# POST /api/garage-requests/admin/{id}/approve
# ──────────────────────────────────────────

@router.post("/admin/{request_id}/approve", response_model=schemas.GarageResponse)
def approve_garage_request(
    request_id: int,
    db: Session = Depends(get_db),
    x_admin_key: str = None
):
    """
    Admin request approve karta hai.
    1. garages table mein naya garage create hota hai
    2. garage_requests mein status approved ho jaata hai
    3. Default working hours ban jaate hain
    4. Empty location row ban jaati hai
    Header: X-Admin-Key: gnm_admin_secret_2026
    """
    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != models.GarageRequestStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Request is already {req.status}"
        )

    # Garage table mein create karo
    new_garage = models.Garage(
        name        = req.garage_name,
        owner_name  = req.owner_name,
        phone       = req.phone,
        email       = req.email,
        garage_type = req.garage_type,
        is_verified = True,    # Admin ne approve kiya toh verified
        is_active   = True,
    )
    db.add(new_garage)
    db.flush()  # ID milne ke liye (commit se pehle)

    # Default working hours — Mon to Sat open, Sun closed
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in days:
        wh = models.GarageWorkingHours(
            garage_id   = new_garage.id,
            day_of_week = day,
            is_open     = day != "sunday",
            open_time   = datetime.strptime("09:00", "%H:%M").time(),
            close_time  = datetime.strptime("20:00", "%H:%M").time(),
        )
        db.add(wh)

    # Location row banao (address request se copy karo)
    location = models.GarageLocation(
        garage_id   = new_garage.id,
        street      = req.address,
        city        = req.city,
        pincode     = req.pincode,
    )
    db.add(location)

    # Request ka status update karo
    req.status = models.GarageRequestStatus.approved

    db.commit()
    db.refresh(new_garage)
    return new_garage


# ──────────────────────────────────────────
# 4. REJECT REQUEST (Admin)
# POST /api/garage-requests/admin/{id}/reject
# ──────────────────────────────────────────

@router.post("/admin/{request_id}/reject", response_model=schemas.GarageRequestResponse)
def reject_garage_request(
    request_id: int,
    update: schemas.GarageRequestAdminUpdate,
    db: Session = Depends(get_db),
    x_admin_key: str = None
):
    """
    Admin request reject karta hai.
    Header: X-Admin-Key: gnm_admin_secret_2026
    """
    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if req.status != models.GarageRequestStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Request is already {req.status}"
        )

    req.status     = models.GarageRequestStatus.rejected
    req.admin_note = update.admin_note

    db.commit()
    db.refresh(req)
    return req

@router.post("/admin/{request_id}/start-review")
def start_review(request_id:int, db:Session=Depends(get_db), x_admin_key :str =None):
    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.status = models.GarageRequestStatus.under_review

    db.commit()

    return {"message": "Review started successfully"}

@router.post("/admin/{request_id}/schedule-visit")
def schedule_visit(
    request_id : int, 
    data : schemas.GarageRequestReviewUpdate, db: Session = Depends(get_db), x_admin_key : str = None ):
    
    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(status_code = 404, detail ="Request not found")

    req.visit_date = date.visit_date
    req.visit_notes = date.visit_notes

    req.status = models.GarageRequestStatus.site_visit_scheduled

    db.commit()

    return {"message":"Site visit scheduled"}