from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, cast, Date
from datetime import datetime
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os
import random
import string

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

def generate_unique_booking_number(db: Session) -> str:
    """
    Generates a unique reference code: BK-[6 uppercase alphanumeric characters]
    """
    while True:
        code = "BK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        exists = db.query(models.Booking).filter(models.Booking.booking_number == code).first()
        if not exists:
            return code


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
    if garage.is_credit_locked:
        raise HTTPException(status_code=403, detail="Garage credit limit exceeded. Bookings are temporarily blocked.")

    pickup_address = booking_data.pickup_address if booking_data.requires_pick_and_drop else None
    booking_no = generate_unique_booking_number(db)

    booking = models.Booking(
        booking_number   = booking_no,
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
    if garage.is_credit_locked:
        raise HTTPException(status_code=403, detail="Garage credit limit exceeded. SOS requests are temporarily blocked.")

    pickup_address = sos_data.pickup_address if sos_data.requires_pick_and_drop else None
    booking_no = generate_unique_booking_number(db)

    booking = models.Booking(
        booking_number   = booking_no,
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

    # Calculate total estimated amount from itemized list
    total_estimate = sum(item.price for item in update.estimate_details)
    booking.estimated_amount = total_estimate
    
    # Store itemized details
    booking.estimate_details = [item.dict() for item in update.estimate_details]
    booking.estimate_status  = update.estimate_status
    booking.has_hidden_issues = update.has_hidden_issues

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


@router.get("/my/past", response_model=schemas.PaginatedBookingResponse)
def get_my_past_bookings(
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer),
    page: int = Query(1, ge=1),
    size: int = Query(15, ge=1, le=100),
    garage_name: str = Query(None),
    status: str = Query(None),
    date: str = Query(None)
):
    """
    Customer ki paginated past history bookings (completed / cancelled)
    GET /api/bookings/my/past
    """
    import math

    # Base query: only past bookings
    query = db.query(models.Booking).join(models.Garage, models.Booking.garage_id == models.Garage.id).filter(
        models.Booking.customer_id == current_customer.id,
        models.Booking.status.in_([models.BookingStatus.completed, models.BookingStatus.cancelled])
    )

    # Filtering
    if garage_name:
        query = query.filter(models.Garage.name.ilike(f"%{garage_name}%"))
        
    if status:
        if status.lower() == 'completed':
            query = query.filter(models.Booking.status == models.BookingStatus.completed)
        elif status.lower() == 'cancelled':
            query = query.filter(models.Booking.status == models.BookingStatus.cancelled)

    if date:
        # Date string usually format YYYY-MM-DD
        try:
            filter_date = datetime.strptime(date, '%Y-%m-%d').date()
            query = query.filter(cast(models.Booking.created_at, Date) == filter_date)
        except ValueError:
            pass # ignore invalid date format

    # Sorting
    query = query.order_by(models.Booking.created_at.desc())

    # Pagination calculation
    total = query.count()
    pages = math.ceil(total / size) if total > 0 else 1
    
    # Apply offset and limit
    items = query.offset((page - 1) * size).limit(size).all()
    
    # Need to inject garage_name properly since the response model requires it or we already have garage loaded
    # Wait, in BookingResponse, garage_name is handled in router sometimes but here SQLAlchemy relationship might not auto-populate it if it's not a property. 
    # Let's populate garage_name explicitly
    for item in items:
        item.garage_name = item.garage.name if item.garage else None

    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }


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


@router.get("/garage/{booking_id}", response_model=schemas.BookingResponse)
def get_garage_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage ke liye ek specific booking ki details.
    GET /api/bookings/garage/{booking_id}
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    return booking


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
        booking.final_amount = update.final_amount

        # Calculate amounts instantly upon completion
        final_amount = float(update.final_amount) if update.final_amount else 0.0
        
        # Calculate subtotal and tax (assuming 18% GST)
        if current_garage.has_gst:
            subtotal = final_amount / 1.18
            tax_amount = final_amount - subtotal
        else:
            subtotal = final_amount
            tax_amount = 0.0
        
        # Collect all items for the bill
        items = []
        if booking.estimate_details:
            items.extend(booking.estimate_details)
        if booking.additional_estimate_details:
            items.extend(booking.additional_estimate_details)
        if booking.pickup_charge and float(booking.pickup_charge) > 0:
            items.append({
                "item_name": "Pick & Drop / Visiting Charge",
                "price": float(booking.pickup_charge),
                "qty": 1
            })
        
        # Garage location address
        garage_address = ""
        if current_garage.location:
            addr_parts = [
                current_garage.location.shop_number,
                current_garage.location.street,
                current_garage.location.city
            ]
            garage_address = ", ".join([p for p in addr_parts if p])
        
        # Vehicle info
        vehicle_info = " • ".join([p for p in [booking.vehicle_model or booking.vehicle_type, booking.vehicle_number] if p])
        
        # Calculate platform commission
        commission_rule = db.query(models.CommissionRule).filter(
            models.CommissionRule.is_active == True,
            models.CommissionRule.min_amount <= final_amount,
            (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
        ).first()

        platform_commission = 0.0
        if commission_rule:
            platform_commission = (final_amount * float(commission_rule.percentage)) / 100.0

        garage_earnings = final_amount - platform_commission

        # Save to booking
        booking.platform_commission = platform_commission
        booking.garage_earnings = garage_earnings

        # Check if bill already exists to prevent duplicate entry
        existing_bill = db.query(models.Bill).filter(models.Bill.booking_id == booking.id).first()
        if not existing_bill:
            bill = models.Bill(
                booking_id=booking.id,
                customer_id=booking.customer_id,
                garage_id=current_garage.id,
                bill_number=f"GNM-{booking.id}-BILL",
                subtotal=subtotal,
                tax_amount=tax_amount,
                total_amount=final_amount,
                platform_commission=platform_commission,
                garage_earnings=garage_earnings,
                items=items,
                garage_name=current_garage.name,
                garage_address=garage_address,
                garage_gst=current_garage.gst_number if current_garage.has_gst else None,
                customer_name=booking.customer_name,
                vehicle_info=vehicle_info,
                service_type=booking.service_type or ("SOS Assistance" if booking.booking_type == models.BookingType.sos else "General Service")
            )
            db.add(bill)

        # Update outstanding platform dues (dues accumulate; weekly billing manages lockouts)
        if current_garage.pending_platform_dues is None:
            current_garage.pending_platform_dues = 0.0
        current_garage.pending_platform_dues = float(current_garage.pending_platform_dues) + float(platform_commission)

    booking.status      = update.status
    booking.garage_note = update.garage_note

    db.commit()
    db.refresh(booking)
    return booking


@router.patch("/garage/{booking_id}/payment")
def update_booking_payment_status(
    booking_id: int,
    status_update: schemas.PaymentStatusUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Update payment status (e.g. mark as 'paid').
    When payment is marked as paid, automatically save bill for customer.
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.payment_status = status_update.payment_status
    db.commit()
    db.refresh(booking)
    
    # If payment is marked as paid, save bill for customer
    if status_update.payment_status == 'paid':
        # Calculate amounts ONLY if they have not been calculated yet (backward compatibility for legacy bookings)
        if booking.platform_commission is None:
            final_amount = float(booking.final_amount) if booking.final_amount else 0
            
            # Calculate subtotal and tax (assuming 18% GST)
            if current_garage.has_gst:
                subtotal = final_amount / 1.18
                tax_amount = final_amount - subtotal
            else:
                subtotal = final_amount
                tax_amount = 0
            
            # Collect all items for the bill
            items = []
            if booking.estimate_details:
                items.extend(booking.estimate_details)
            if booking.additional_estimate_details:
                items.extend(booking.additional_estimate_details)
            if booking.pickup_charge and float(booking.pickup_charge) > 0:
                items.append({
                    "item_name": "Pick & Drop / Visiting Charge",
                    "price": float(booking.pickup_charge),
                    "qty": 1
                })
            
            # Garage location address
            garage_address = ""
            if current_garage.location:
                addr_parts = [
                    current_garage.location.shop_number,
                    current_garage.location.street,
                    current_garage.location.city
                ]
                garage_address = ", ".join([p for p in addr_parts if p])
            
            # Vehicle info
            vehicle_info = " • ".join([p for p in [booking.vehicle_model or booking.vehicle_type, booking.vehicle_number] if p])
            
            # Calculate platform commission
            commission_rule = db.query(models.CommissionRule).filter(
                models.CommissionRule.is_active == True,
                models.CommissionRule.min_amount <= final_amount,
                (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
            ).first()

            platform_commission = 0.0
            if commission_rule:
                platform_commission = (final_amount * float(commission_rule.percentage)) / 100.0

            garage_earnings = final_amount - platform_commission

            # Save to booking
            booking.platform_commission = platform_commission
            booking.garage_earnings = garage_earnings

            # Create bill if it doesn't exist
            existing_bill = db.query(models.Bill).filter(models.Bill.booking_id == booking.id).first()
            if not existing_bill:
                bill = models.Bill(
                    booking_id=booking.id,
                    customer_id=booking.customer_id,
                    garage_id=current_garage.id,
                    bill_number=f"GNM-{booking.id}-BILL",
                    subtotal=subtotal,
                    tax_amount=tax_amount,
                    total_amount=final_amount,
                    platform_commission=platform_commission,
                    garage_earnings=garage_earnings,
                    items=items,
                    garage_name=current_garage.name,
                    garage_address=garage_address,
                    garage_gst=current_garage.gst_number if current_garage.has_gst else None,
                    customer_name=booking.customer_name,
                    vehicle_info=vehicle_info,
                    service_type=booking.service_type or (models.BookingType.sos.value if booking.booking_type == models.BookingType.sos else "General Service")
                )
                db.add(bill)

            # Update outstanding platform dues (dues accumulate; weekly billing manages lockouts)
            if current_garage.pending_platform_dues is None:
                current_garage.pending_platform_dues = 0.0
            current_garage.pending_platform_dues = float(current_garage.pending_platform_dues) + float(platform_commission)

            db.commit()
    
    # Return as dict and inject garage info
    booking_data = schemas.BookingResponse.model_validate(booking).model_dump()
    booking_data['garage_visiting_charge'] = float(current_garage.visiting_charge) if current_garage.visiting_charge else None
    booking_data['garage_name'] = current_garage.name
    return booking_data


# ──────────────────────────────────────────
# SEND ESTIMATE OTP (Garage → Customer)
# POST /api/bookings/{booking_id}/send-estimate-otp
# ──────────────────────────────────────────

import random

@router.post("/{booking_id}/send-estimate-otp")
def send_estimate_otp(
    booking_id: int,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage estimate bhejne ke baad OTP customer ke phone pe jaata hai.
    Customer OTP de toh kaam shuru.
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.estimate_status != models.EstimateStatus.pending:
        raise HTTPException(status_code=400, detail="Estimate must be sent first")

    otp = str(random.randint(100000, 999999))
    booking.estimate_otp          = otp
    booking.estimate_otp_verified = False
    booking.estimate_otp_sent_at  = datetime.utcnow()
    db.commit()

    # TODO: SMS send karo customer ke phone pe
    print(f"\n{'='*40}")
    print(f"ESTIMATE OTP for Booking #{booking_id}: {otp}")
    print(f"Customer phone: {booking.customer.phone}")
    print(f"{'='*40}\n")

    return {
        "message": "OTP sent to customer",
        "otp": otp  # TESTING ONLY
    }


# ──────────────────────────────────────────
# VERIFY ESTIMATE OTP (Garage verifies customer OTP)
# POST /api/bookings/{booking_id}/verify-estimate-otp
# ──────────────────────────────────────────

@router.post("/{booking_id}/verify-estimate-otp", response_model=schemas.BookingResponse)
def verify_estimate_otp(
    booking_id: int,
    otp: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Customer ka OTP verify karo → booking ongoing ho jaati hai.
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.estimate_otp != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if booking.estimate_otp_verified:
        raise HTTPException(status_code=400, detail="OTP already used")

    booking.estimate_otp_verified = True
    booking.estimate_status       = models.EstimateStatus.approved
    booking.status                = models.BookingStatus.ongoing
    booking.started_at            = datetime.utcnow()
    db.commit()
    db.refresh(booking)
    return booking


# ──────────────────────────────────────────
# SEND ADDITIONAL ESTIMATE (Hidden Issues mile)
# PATCH /api/bookings/{booking_id}/additional-estimate
# ──────────────────────────────────────────

from pydantic import BaseModel
from typing import List, Optional

class AdditionalEstimateItem(BaseModel):
    item_name: str
    price: float

class AdditionalEstimatePayload(BaseModel):
    items: List[AdditionalEstimateItem]
    note: Optional[str] = None

@router.patch("/{booking_id}/additional-estimate")
def send_additional_estimate(
    booking_id: int,
    payload: AdditionalEstimatePayload,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Hidden issues mile → additional estimate bhejo.
    Customer ka OTP 2 lena hoga kaam shuru karne ke liye.
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id,
        models.Booking.status    == models.BookingStatus.ongoing
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not ongoing")

    total = sum(item.price for item in payload.items)
    booking.additional_estimate         = total
    booking.additional_estimate_note    = payload.note
    booking.additional_estimate_details = [i.dict() for i in payload.items]

    # Send OTP 2
    otp = str(random.randint(100000, 999999))
    booking.additional_otp          = otp
    booking.additional_otp_verified = False
    booking.additional_otp_sent_at  = datetime.utcnow()
    db.commit()
    db.refresh(booking)

    print(f"\n{'='*40}")
    print(f"ADDITIONAL OTP for Booking #{booking_id}: {otp}")
    print(f"{'='*40}\n")

    return {
        "message": "Additional estimate sent, OTP generated",
        "additional_estimate": total,
        "otp": otp  # TESTING ONLY
    }


# ──────────────────────────────────────────
# VERIFY ADDITIONAL OTP
# POST /api/bookings/{booking_id}/verify-additional-otp
# ──────────────────────────────────────────

@router.post("/{booking_id}/verify-additional-otp", response_model=schemas.BookingResponse)
def verify_additional_otp(
    booking_id: int,
    otp: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Customer OTP 2 deta hai → additional kaam bhi start.
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not booking.additional_otp:
        raise HTTPException(status_code=400, detail="No additional estimate sent")
    if booking.additional_otp != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if booking.additional_otp_verified:
        raise HTTPException(status_code=400, detail="OTP already used")

    booking.additional_otp_verified = True
    db.commit()
    db.refresh(booking)
    return booking


# ──────────────────────────────────────────
# GET BILL (Customer → View Bill)
# GET /api/bookings/{booking_id}/bill
# ──────────────────────────────────────────

@router.get("/{booking_id}/bill", response_model=schemas.BillResponse)
def get_booking_bill(
    booking_id: int,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    Customer apne booking ka bill dekh sakta hai.
    Bill sirf paid bookings mein hoga.
    GET /api/bookings/{booking_id}/bill
    """
    booking = db.query(models.Booking).filter(
        models.Booking.id           == booking_id,
        models.Booking.customer_id  == current_customer.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    bill = db.query(models.Bill).filter(
        models.Bill.booking_id == booking_id
    ).first()

    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found. Payment may not have been marked as paid yet.")

    return bill