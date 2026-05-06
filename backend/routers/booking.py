from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os

import models, schemas
from database import get_db

router = APIRouter()

SECRET_KEY  = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM   = os.getenv("ALGORITHM", "HS256")

customer_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
garage_oauth2   = OAuth2PasswordBearer(tokenUrl="/api/garage/login")


# ──────────────────────────────────────────
# AUTH HELPERS
# ──────────────────────────────────────────

def get_current_customer(
    token: str = Depends(customer_oauth2),
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


def get_current_garage(
    token: str = Depends(garage_oauth2),
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
        raise HTTPException(status_code=401, detail="Invalid token")


# ──────────────────────────────────────────
# CUSTOMER ENDPOINTS
# ──────────────────────────────────────────

@router.post("/", response_model=schemas.BookingResponse, status_code=201)
def create_booking(
    booking_data: schemas.BookingCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    Customer normal booking karta hai — garage select karke.
    POST /api/bookings/
    """
    # Garage exist karta hai?
    garage = db.query(models.Garage).filter(
        models.Garage.id == booking_data.garage_id,
        models.Garage.is_active == True
    ).first()
    if not garage:
        raise HTTPException(status_code=404, detail="Garage not found or inactive")

    pickup_address = booking_data.pickup_address if booking_data.requires_pick_and_drop else None

    booking = models.Booking(
        customer_id      = current_customer.id,
        garage_id        = booking_data.garage_id,
        booking_type     = booking_data.booking_type,
        vehicle_type     = booking_data.vehicle_type,
        vehicle_model    = booking_data.vehicle_model,
        vehicle_number   = booking_data.vehicle_number,
        service_type     = booking_data.service_type,
        description      = booking_data.description,
        customer_lat     = booking_data.customer_lat,
        customer_lng     = booking_data.customer_lng,
        customer_address = booking_data.customer_address,
        scheduled_at     = booking_data.scheduled_at,
        requires_pick_and_drop = booking_data.requires_pick_and_drop,
        pickup_address   = pickup_address,
        pickup_charge    = None,
        status           = models.BookingStatus.pending,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/sos", response_model=schemas.BookingResponse, status_code=201)
def create_sos_booking(
    sos_data: schemas.SOSBookingCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    SOS emergency booking — customer ki lat/lng zaroori hai.
    POST /api/bookings/sos
    Baad mein: nearest garage automatically select hoga PostGIS se.
    Abhi: customer manually garage_id deta hai.
    """
    garage = db.query(models.Garage).filter(
        models.Garage.id == sos_data.garage_id,
        models.Garage.is_active == True,
        models.Garage.is_sos_available == True  # SOS ke liye available hona chahiye
    ).first()
    if not garage:
        raise HTTPException(status_code=404, detail="No SOS-available garage found")

    pickup_address = sos_data.pickup_address if sos_data.requires_pick_and_drop else None

    booking = models.Booking(
        customer_id      = current_customer.id,
        garage_id        = sos_data.garage_id,
        booking_type     = models.BookingType.sos,
        vehicle_type     = sos_data.vehicle_type,
        vehicle_model    = sos_data.vehicle_model,
        vehicle_number   = sos_data.vehicle_number,
        description      = sos_data.description,
        customer_lat     = sos_data.customer_lat,
        customer_lng     = sos_data.customer_lng,
        customer_address = sos_data.customer_address,
        requires_pick_and_drop = sos_data.requires_pick_and_drop,
        pickup_address   = pickup_address,
        pickup_charge    = None,
        status           = models.BookingStatus.pending,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.patch("/{booking_id}/approve-estimate", response_model=schemas.BookingResponse)
def approve_booking_estimate(
    booking_id: int,
    update: schemas.EstimateApproval,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    Customer estimate approve/reject karta hai.
    PATCH /api/bookings/{booking_id}/approve-estimate
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id          == booking_id,
        models.Booking.customer_id == current_customer.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.estimate_status != models.EstimateStatus.pending:
        raise HTTPException(
            status_code=400,
            detail="No pending estimate to approve or reject"
        )

    if update.estimate_status not in [
        schemas.EstimateStatus.approved,
        schemas.EstimateStatus.rejected,
    ]:
        raise HTTPException(status_code=400, detail="Only approved or rejected is allowed")

    booking.estimate_status = models.EstimateStatus(update.estimate_status.value)
    if update.estimate_status == schemas.EstimateStatus.rejected:
        booking.status = models.BookingStatus.cancelled

    db.commit()
    db.refresh(booking)
    return booking


@router.patch("/{booking_id}/estimate", response_model=schemas.BookingResponse)
def update_booking_estimate(
    booking_id: int,
    update: schemas.BookingEstimateUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage booking ka estimate bhejta hai.
    PATCH /api/bookings/{booking_id}/estimate
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if not booking.requires_pick_and_drop:
        booking.pickup_charge = None
        if update.pickup_charge is not None:
            raise HTTPException(
                status_code=400,
                detail="Pick & Drop was not requested for this booking"
            )
    else:
        booking.pickup_charge = update.pickup_charge

    booking.estimated_amount = update.estimated_amount
    booking.estimate_status  = update.estimate_status

    db.commit()
    db.refresh(booking)
    return booking


@router.get("/my", response_model=list[schemas.BookingResponse])
def get_my_bookings(
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    Customer apni saari bookings dekhe.
    GET /api/bookings/my
    """
    return db.query(models.Booking).filter(
        models.Booking.customer_id == current_customer.id
    ).order_by(models.Booking.created_at.desc()).all()


@router.delete("/{booking_id}", status_code=204)
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    Customer pending booking cancel kar sakta hai.
    DELETE /api/bookings/{booking_id}
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id          == booking_id,
        models.Booking.customer_id == current_customer.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status != models.BookingStatus.pending:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel booking with status '{booking.status}'"
        )

    booking.status = models.BookingStatus.cancelled
    db.commit()
    return None


# ──────────────────────────────────────────
# GARAGE ENDPOINTS
# ──────────────────────────────────────────

@router.get("/garage/incoming", response_model=list[schemas.BookingResponse])
def get_incoming_bookings(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage ko aane wali saari pending bookings dikho.
    GET /api/bookings/garage/incoming
    Dashboard ka "Recent Bookings" section yahi use karega.
    """
    return db.query(models.Booking).filter(
        models.Booking.garage_id == current_garage.id,
        models.Booking.status    == models.BookingStatus.pending
    ).order_by(models.Booking.created_at.desc()).all()


@router.get("/garage/all", response_model=list[schemas.BookingResponse])
def get_all_garage_bookings(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage ki saari bookings — history ke liye.
    GET /api/bookings/garage/all
    """
    return db.query(models.Booking).filter(
        models.Booking.garage_id == current_garage.id
    ).order_by(models.Booking.created_at.desc()).all()


@router.patch("/{booking_id}/status", response_model=schemas.BookingResponse)
def update_booking_status(
    booking_id: int,
    update: schemas.BookingStatusUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage booking ka status update karta hai.
    PATCH /api/bookings/{booking_id}/status

    Flow:
    pending   → accepted / rejected
    accepted  → ongoing
    ongoing   → completed
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id       == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Valid transitions check
    valid_transitions = {
        models.BookingStatus.pending:  [models.BookingStatus.accepted, models.BookingStatus.rejected],
        models.BookingStatus.accepted: [models.BookingStatus.ongoing],
        models.BookingStatus.ongoing:  [models.BookingStatus.completed],
    }

    allowed = valid_transitions.get(booking.status, [])
    if update.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot move from '{booking.status}' to '{update.status}'"
        )

    # Timeline timestamps
    now = datetime.utcnow()
    if update.status in [models.BookingStatus.accepted, models.BookingStatus.rejected]:
        booking.responded_at = now
    elif update.status == models.BookingStatus.ongoing:
        booking.started_at = now
    elif update.status == models.BookingStatus.completed:
        booking.completed_at = now

    booking.status      = update.status
    booking.garage_note = update.garage_note

    db.commit()
    db.refresh(booking)
    return booking
