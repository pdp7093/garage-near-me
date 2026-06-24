from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, cast, Date
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os
import random
import string
import re
import unicodedata

import models, schemas
from database import get_db
from routers.fcm import GarageNotifications, CustomerNotifications
from routers.auth import send_whatsapp_otp

router = APIRouter()

SECRET_KEY  = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM   = os.getenv("ALGORITHM", "HS256")

customer_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
garage_oauth2   = OAuth2PasswordBearer(tokenUrl="/api/garage/login")

VISITING_CHARGE = 100.0  # ₹100 fixed visiting charge on estimate reject


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
    while True:
        code = "BK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        exists = db.query(models.Booking).filter(models.Booking.booking_number == code).first()
        if not exists:
            return code


def _resolve_booking(slug_or_id: str, db: Session) -> models.Booking | None:
    try:
        return db.query(models.Booking).filter(models.Booking.id == int(slug_or_id)).first()
    except (ValueError, TypeError):
        return db.query(models.Booking).filter(models.Booking.slug == slug_or_id).first()


def _make_booking_slug(booking_number: str, booking_id: int) -> str:
    s = unicodedata.normalize("NFKD", booking_number).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return f"{s}-{booking_id}"


def _generate_visiting_charge_bill(booking: models.Booking, garage: models.Garage, db: Session):
    """
    ₹100 visiting charge bill generate karo jab customer estimate reject kare.
    """
    existing_bill = db.query(models.Bill).filter(models.Bill.booking_id == booking.id).first()
    if existing_bill:
        return existing_bill  # Already exists

    garage_address = ""
    if garage.location:
        addr_parts = [garage.location.shop_number, garage.location.street, garage.location.city]
        garage_address = ", ".join([p for p in addr_parts if p])

    vehicle_info = " • ".join([p for p in [booking.vehicle_model or booking.vehicle_type, booking.vehicle_number] if p])

    items = [{"item_name": "Visiting Charge", "price": VISITING_CHARGE, "qty": 1}]

    # Commission on ₹100 — fixed slab (₹40 fixed for small jobs)
    commission_rule = db.query(models.CommissionRule).filter(
        models.CommissionRule.is_active == True,
        models.CommissionRule.min_amount <= VISITING_CHARGE,
        (models.CommissionRule.max_amount >= VISITING_CHARGE) | (models.CommissionRule.max_amount == None)
    ).first()

    platform_commission = 0.0
    if commission_rule:
        if commission_rule.is_fixed:
            platform_commission = float(commission_rule.fixed_amount or 0)
        else:
            platform_commission = (VISITING_CHARGE * float(commission_rule.percentage)) / 100.0

    garage_earnings = VISITING_CHARGE - platform_commission

    bill = models.Bill(
        booking_id=booking.id,
        customer_id=booking.customer_id,
        garage_id=garage.id,
        bill_number=f"GNM-{booking.id}-VISIT",
        subtotal=VISITING_CHARGE,
        tax_amount=0.0,
        total_amount=VISITING_CHARGE,
        platform_commission=platform_commission,
        garage_earnings=garage_earnings,
        items=items,
        garage_name=garage.name,
        garage_address=garage_address,
        garage_gst=None,
        customer_name=booking.customer.name if booking.customer else None,
        vehicle_info=vehicle_info,
        service_type="Visiting Charge — Estimate Rejected"
    )
    db.add(bill)

    # Garage dues update
    if garage.pending_platform_dues is None:
        garage.pending_platform_dues = 0.0
    garage.pending_platform_dues = float(garage.pending_platform_dues) + platform_commission

    # Trial check
    if not garage.has_completed_trial and garage.pending_platform_dues >= 500.0:
        garage.has_completed_trial = True

    booking.visiting_charge_billed = True
    booking.final_amount = VISITING_CHARGE

    db.commit()
    return bill


# ──────────────────────────────────────────
# CUSTOMER ENDPOINTS
# ──────────────────────────────────────────

@router.post("/", response_model=schemas.BookingResponse, status_code=201)
def create_booking(
    booking_data: schemas.BookingCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
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
    booking.slug = _make_booking_slug(booking.booking_number, booking.id)
    db.commit()
    db.refresh(booking)

    if garage.fcm_token:
        GarageNotifications.new_booking(
            token=garage.fcm_token,
            booking_id=booking.id,
            customer_name=current_customer.name,
            service=booking.service_type or "General Service"
        )

    return booking


@router.post("/sos", response_model=schemas.BookingResponse, status_code=201)
def create_sos_booking(
    sos_data: schemas.SOSBookingCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    garage = db.query(models.Garage).filter(
        models.Garage.id == sos_data.garage_id,
        models.Garage.is_active == True,
        models.Garage.is_sos_available == True
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
    booking.slug = _make_booking_slug(booking.booking_number, booking.id)
    db.commit()
    db.refresh(booking)
    return booking


# ──────────────────────────────────────────
# APPROVE / REJECT ESTIMATE
# ──────────────────────────────────────────

@router.patch("/{booking_id}/approve-estimate", response_model=schemas.BookingResponse)
def approve_booking_estimate(
    booking_id: int,
    update: schemas.EstimateApproval,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    booking = db.query(models.Booking).filter(
        models.Booking.id          == booking_id,
        models.Booking.customer_id == current_customer.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.estimate_status != models.EstimateStatus.pending:
        raise HTTPException(status_code=400, detail="No pending estimate to approve or reject")

    if update.estimate_status not in [schemas.EstimateStatus.approved, schemas.EstimateStatus.rejected]:
        raise HTTPException(status_code=400, detail="Only approved or rejected is allowed")

    booking.estimate_status = models.EstimateStatus(update.estimate_status.value)

    if update.estimate_status == schemas.EstimateStatus.rejected:
        booking.status = models.BookingStatus.cancelled
        booking.completed_at = datetime.utcnow()

        # ✅ ₹100 visiting charge bill generate karo
        garage = db.query(models.Garage).filter(models.Garage.id == booking.garage_id).first()
        if garage:
            _generate_visiting_charge_bill(booking, garage, db)

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
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if not booking.requires_pick_and_drop:
        booking.pickup_charge = None
        if update.pickup_charge is not None:
            raise HTTPException(status_code=400, detail="Pick & Drop was not requested for this booking")
    else:
        booking.pickup_charge = update.pickup_charge

    total_estimate = sum(item.price for item in update.estimate_details)
    if booking.pickup_charge:
        total_estimate += float(booking.pickup_charge)

    booking.estimated_amount  = total_estimate
    booking.estimate_details  = [item.dict() for item in update.estimate_details]
    booking.estimate_status   = update.estimate_status
    booking.has_hidden_issues = update.has_hidden_issues

    db.commit()
    db.refresh(booking)
    return booking


# ──────────────────────────────────────────
# ADMIN — ALL BOOKINGS
# ──────────────────────────────────────────

@router.get("/admin/all")
def admin_get_all_bookings(
    page: int = 1,
    limit: int = 20,
    type: str = None,
    status_filter: str = None,
    search: str = None,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):
    from routers.garage_requests import check_admin
    if not x_admin_key:
        raise HTTPException(status_code=401, detail="Admin key required")
    check_admin(x_admin_key)

    query = db.query(models.Booking)

    if type in ("normal", "sos"):
        query = query.filter(models.Booking.booking_type == models.BookingType(type))

    if status_filter:
        try:
            query = query.filter(models.Booking.status == models.BookingStatus(status_filter))
        except ValueError:
            pass

    if search:
        like = f"%{search}%"
        query = query.join(models.Customer, models.Booking.customer_id == models.Customer.id, isouter=True)
        query = query.filter(or_(
            models.Booking.booking_number.ilike(like),
            models.Customer.name.ilike(like),
            models.Customer.phone.ilike(like),
        ))

    total = query.count()
    bookings = query.order_by(models.Booking.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    now = datetime.utcnow()
    rows = []
    for b in bookings:
        garage = db.query(models.Garage).filter(models.Garage.id == b.garage_id).first()
        garage_loc = garage.location if garage and garage.location else None
        rows.append({
            "id":             b.id,
            "slug":           b.slug,
            "booking_number": b.booking_number,
            "booking_type":   b.booking_type.value,
            "status":         b.status.value,
            "customer_name":  b.customer.name if b.customer else "—",
            "customer_phone": b.customer.phone if b.customer else "—",
            "vehicle_model":  b.vehicle_model or b.vehicle_type,
            "garage_name":    garage.name if garage else "—",
            "garage_city":    garage_loc.city if garage_loc else "—",
            "final_amount":   float(b.final_amount) if b.final_amount else None,
            "payment_status": b.payment_status,
            "created_at":     b.created_at.isoformat() if b.created_at else None,
        })

    return {"total": total, "page": page, "limit": limit, "bookings": rows}


# ──────────────────────────────────────────
# CANCEL BOOKING (Customer)
# ──────────────────────────────────────────

@router.post("/{booking_id}/cancel")
def cancel_booking_post(
    booking_id: int,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    booking = db.query(models.Booking).filter(
        models.Booking.id          == booking_id,
        models.Booking.customer_id == current_customer.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # ✅ Sirf pending ya accepted cancel ho sakti hai
    if booking.status not in [models.BookingStatus.pending, models.BookingStatus.accepted]:
        raise HTTPException(status_code=400, detail="Sirf pending ya accepted booking cancel ho sakti hai.")

    # ✅ 1 hour lock — agar mechanic ne accept kar liya aur slot 1hr se kam bacha hai
    if booking.status == models.BookingStatus.accepted and booking.scheduled_at:
        now_utc = datetime.utcnow()
        scheduled = booking.scheduled_at
        # Remove tzinfo agar aware datetime hai
        if scheduled.tzinfo is not None:
            scheduled = scheduled.replace(tzinfo=None)
        time_left = scheduled - now_utc
        if time_left.total_seconds() < 3600:  # 1 hour = 3600 seconds
            raise HTTPException(
                status_code=400,
                detail="Slot se 1 ghante pehle booking cancel nahi ho sakti."
            )

    booking.status       = models.BookingStatus.cancelled
    booking.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)

    if booking.garage and booking.garage.fcm_token:
        GarageNotifications.booking_cancelled(token=booking.garage.fcm_token, booking_id=booking_id)

    return {"message": "Booking successfully cancelled", "booking_id": booking_id, "status": "cancelled"}


@router.get("/my", response_model=list[schemas.BookingResponse])
def get_my_bookings(
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
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
    import math

    query = db.query(models.Booking).join(models.Garage, models.Booking.garage_id == models.Garage.id).filter(
        models.Booking.customer_id == current_customer.id,
        models.Booking.status.in_([models.BookingStatus.completed, models.BookingStatus.cancelled])
    )

    if garage_name:
        query = query.filter(models.Garage.name.ilike(f"%{garage_name}%"))
    if status:
        if status.lower() == 'completed':
            query = query.filter(models.Booking.status == models.BookingStatus.completed)
        elif status.lower() == 'cancelled':
            query = query.filter(models.Booking.status == models.BookingStatus.cancelled)
    if date:
        try:
            filter_date = datetime.strptime(date, '%Y-%m-%d').date()
            query = query.filter(cast(models.Booking.created_at, Date) == filter_date)
        except ValueError:
            pass

    query = query.order_by(models.Booking.created_at.desc())
    total = query.count()
    pages = math.ceil(total / size) if total > 0 else 1
    items = query.offset((page - 1) * size).limit(size).all()

    for item in items:
        item.garage_name = item.garage.name if item.garage else None

    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


@router.get("/{booking_slug_or_id}", response_model=schemas.BookingResponse)
def get_customer_booking(
    booking_slug_or_id: str,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    booking = _resolve_booking(booking_slug_or_id, db)
    if not booking or booking.customer_id != current_customer.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.garage:
        booking.garage_name = booking.garage.name
        loc = booking.garage.location
        if loc:
            parts = [loc.shop_number, loc.street, loc.city]
            booking.garage_address = ", ".join(p for p in parts if p)
    return booking


@router.delete("/{booking_id}", status_code=204)
def cancel_booking_delete(
    booking_id: int,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    booking = db.query(models.Booking).filter(
        models.Booking.id          == booking_id,
        models.Booking.customer_id == current_customer.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # ✅ Pending — free cancel
    if booking.status == models.BookingStatus.pending:
        booking.status = models.BookingStatus.cancelled
        db.commit()
        return None

    # ✅ Accepted — 1hr lock check
    if booking.status == models.BookingStatus.accepted:
        if booking.scheduled_at:
            now_utc = datetime.utcnow()
            scheduled = booking.scheduled_at
            if scheduled.tzinfo is not None:
                scheduled = scheduled.replace(tzinfo=None)
            time_left = scheduled - now_utc
            if time_left.total_seconds() < 3600:
                raise HTTPException(
                    status_code=400,
                    detail="Slot se 1 ghante pehle booking cancel nahi ho sakti."
                )
        booking.status = models.BookingStatus.cancelled
        booking.completed_at = datetime.utcnow()
        db.commit()
        return None

    raise HTTPException(status_code=400, detail=f"Cannot cancel booking with status '{booking.status.value}'")


# ──────────────────────────────────────────
# GARAGE ENDPOINTS
# ──────────────────────────────────────────

@router.get("/garage/incoming", response_model=list[schemas.BookingResponse])
def get_incoming_bookings(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    return db.query(models.Booking).filter(
        models.Booking.garage_id == current_garage.id,
        models.Booking.status    == models.BookingStatus.pending
    ).order_by(models.Booking.created_at.desc()).all()


@router.get("/garage/all", response_model=list[schemas.BookingResponse])
def get_all_garage_bookings(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    return db.query(models.Booking).filter(
        models.Booking.garage_id == current_garage.id
    ).order_by(models.Booking.created_at.desc()).all()


@router.get("/garage/{booking_slug_or_id}", response_model=schemas.BookingResponse)
def get_garage_booking(
    booking_slug_or_id: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    booking = _resolve_booking(booking_slug_or_id, db)
    if not booking or booking.garage_id != current_garage.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    return booking


@router.patch("/{booking_id}/status", response_model=schemas.BookingResponse)
def update_booking_status(
    booking_id: int,
    update: schemas.BookingStatusUpdate,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    booking = db.query(models.Booking).filter(
        models.Booking.id       == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    valid_transitions = {
        models.BookingStatus.pending:  [models.BookingStatus.accepted, models.BookingStatus.rejected],
        models.BookingStatus.accepted: [models.BookingStatus.ongoing],
        models.BookingStatus.ongoing:  [models.BookingStatus.completed],
    }

    allowed = valid_transitions.get(booking.status, [])
    if update.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Cannot move from '{booking.status}' to '{update.status}'")

    now = datetime.utcnow()
    if update.status in [models.BookingStatus.accepted, models.BookingStatus.rejected]:
        booking.responded_at = now
    elif update.status == models.BookingStatus.ongoing:
        booking.started_at = now
    elif update.status == models.BookingStatus.completed:
        booking.completed_at = now
        booking.final_amount = update.final_amount

        final_amount = float(update.final_amount) if update.final_amount else 0.0

        if current_garage.has_gst:
            subtotal = final_amount / 1.18
            tax_amount = final_amount - subtotal
        else:
            subtotal = final_amount
            tax_amount = 0.0

        items = []
        if booking.estimate_details:
            items.extend(booking.estimate_details)
        if booking.additional_estimate_details:
            items.extend(booking.additional_estimate_details)
        if booking.pickup_charge and float(booking.pickup_charge) > 0:
            items.append({"item_name": "Pick & Drop / Visiting Charge", "price": float(booking.pickup_charge), "qty": 1})

        garage_address = ""
        if current_garage.location:
            addr_parts = [current_garage.location.shop_number, current_garage.location.street, current_garage.location.city]
            garage_address = ", ".join([p for p in addr_parts if p])

        vehicle_info = " • ".join([p for p in [booking.vehicle_model or booking.vehicle_type, booking.vehicle_number] if p])

        commission_rule = db.query(models.CommissionRule).filter(
            models.CommissionRule.is_active == True,
            models.CommissionRule.min_amount <= final_amount,
            (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
        ).first()

        platform_commission = 0.0
        if commission_rule:
            platform_commission = (final_amount * float(commission_rule.percentage)) / 100.0

        garage_earnings = final_amount - platform_commission
        booking.platform_commission = platform_commission
        booking.garage_earnings = garage_earnings

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

        if current_garage.pending_platform_dues is None:
            current_garage.pending_platform_dues = 0.0
        current_garage.pending_platform_dues = float(current_garage.pending_platform_dues) + float(platform_commission)

        if not current_garage.has_completed_trial and current_garage.pending_platform_dues >= 500.0:
            current_garage.has_completed_trial = True

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
    booking = db.query(models.Booking).filter(
        models.Booking.id        == booking_id,
        models.Booking.garage_id == current_garage.id
    ).first()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.payment_status = status_update.payment_status
    db.commit()
    db.refresh(booking)

    if status_update.payment_status == 'paid':
        if booking.platform_commission is None:
            final_amount = float(booking.final_amount) if booking.final_amount else 0

            if current_garage.has_gst:
                subtotal = final_amount / 1.18
                tax_amount = final_amount - subtotal
            else:
                subtotal = final_amount
                tax_amount = 0

            items = []
            if booking.estimate_details:
                items.extend(booking.estimate_details)
            if booking.additional_estimate_details:
                items.extend(booking.additional_estimate_details)
            if booking.pickup_charge and float(booking.pickup_charge) > 0:
                items.append({"item_name": "Pick & Drop / Visiting Charge", "price": float(booking.pickup_charge), "qty": 1})

            garage_address = ""
            if current_garage.location:
                addr_parts = [current_garage.location.shop_number, current_garage.location.street, current_garage.location.city]
                garage_address = ", ".join([p for p in addr_parts if p])

            vehicle_info = " • ".join([p for p in [booking.vehicle_model or booking.vehicle_type, booking.vehicle_number] if p])

            commission_rule = db.query(models.CommissionRule).filter(
                models.CommissionRule.is_active == True,
                models.CommissionRule.min_amount <= final_amount,
                (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
            ).first()

            platform_commission = 0.0
            if commission_rule:
                platform_commission = (final_amount * float(commission_rule.percentage)) / 100.0

            garage_earnings = final_amount - platform_commission
            booking.platform_commission = platform_commission
            booking.garage_earnings = garage_earnings

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

            if current_garage.pending_platform_dues is None:
                current_garage.pending_platform_dues = 0.0
            current_garage.pending_platform_dues = float(current_garage.pending_platform_dues) + float(platform_commission)

            if not current_garage.has_completed_trial and current_garage.pending_platform_dues >= 500.0:
                current_garage.has_completed_trial = True

            db.commit()

    booking_data = schemas.BookingResponse.model_validate(booking).model_dump()
    booking_data['garage_visiting_charge'] = float(current_garage.visiting_charge) if current_garage.visiting_charge else None
    booking_data['garage_name'] = current_garage.name
    return booking_data


# ──────────────────────────────────────────
# SEND ESTIMATE OTP (Garage → Customer)
# ──────────────────────────────────────────

@router.post("/{booking_id}/send-estimate-otp")
async def send_estimate_otp(
    booking_id: int,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
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

    print(f"\n{'='*40}")
    print(f"ESTIMATE OTP for Booking #{booking_id}: {otp}")
    print(f"Customer phone: {booking.customer.phone}")
    print(f"{'='*40}\n")

    customer = db.query(models.Customer).filter(models.Customer.id == booking.customer_id).first()
    if customer and customer.phone:
        try:
            await send_whatsapp_otp(customer.phone, otp)
        except Exception as e:
            print(f"[OTP] WhatsApp send error: {e}")

    if booking.customer and booking.customer.fcm_token and booking.estimated_amount:
        CustomerNotifications.estimate_ready(
            token=booking.customer.fcm_token,
            booking_id=booking_id,
            amount=float(booking.estimated_amount)
        )

    return {"message": "OTP sent to customer", "otp": otp}


# ──────────────────────────────────────────
# VERIFY ESTIMATE OTP
# ──────────────────────────────────────────

@router.post("/{booking_id}/verify-estimate-otp", response_model=schemas.BookingResponse)
def verify_estimate_otp(
    booking_id: int,
    otp: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
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
# SEND ADDITIONAL ESTIMATE
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
async def send_additional_estimate(
    booking_id: int,
    payload: AdditionalEstimatePayload,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
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

    otp = str(random.randint(100000, 999999))
    booking.additional_otp          = otp
    booking.additional_otp_verified = False
    booking.additional_otp_sent_at  = datetime.utcnow()
    db.commit()
    db.refresh(booking)

    print(f"\n{'='*40}")
    print(f"ADDITIONAL OTP for Booking #{booking_id}: {otp}")
    print(f"{'='*40}\n")

    customer = db.query(models.Customer).filter(models.Customer.id == booking.customer_id).first()
    if customer and customer.phone:
        try:
            await send_whatsapp_otp(customer.phone, otp)
        except Exception as e:
            print(f"[OTP] WhatsApp send error: {e}")

    return {"message": "Additional estimate sent, OTP generated", "additional_estimate": total, "otp": otp}


# ──────────────────────────────────────────
# VERIFY ADDITIONAL OTP — Garage side
# ──────────────────────────────────────────

@router.post("/{booking_id}/verify-additional-otp", response_model=schemas.BookingResponse)
def verify_additional_otp(
    booking_id: int,
    otp: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
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
# VERIFY ADDITIONAL OTP — Customer side
# ──────────────────────────────────────────

@router.post("/{booking_id}/customer-verify-additional-otp", response_model=schemas.BookingResponse)
def customer_verify_additional_otp(
    booking_id: int,
    otp: str,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    booking = db.query(models.Booking).filter(
        models.Booking.id          == booking_id,
        models.Booking.customer_id == current_customer.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not booking.additional_otp:
        raise HTTPException(status_code=400, detail="No additional estimate sent yet")
    if booking.additional_otp != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP. Please check your WhatsApp.")
    if booking.additional_otp_verified:
        raise HTTPException(status_code=400, detail="OTP already used")

    booking.additional_otp_verified = True
    db.commit()
    db.refresh(booking)
    return booking


# ──────────────────────────────────────────
# REJECT ADDITIONAL ESTIMATE — Customer side
# ₹100 visiting charge bill generate hoga
# ──────────────────────────────────────────

@router.post("/{booking_id}/reject-additional-estimate")
def reject_additional_estimate(
    booking_id: int,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    booking = db.query(models.Booking).filter(
        models.Booking.id          == booking_id,
        models.Booking.customer_id == current_customer.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if not booking.additional_estimate:
        raise HTTPException(status_code=400, detail="No additional estimate to reject")
    if booking.additional_otp_verified:
        raise HTTPException(status_code=400, detail="Additional estimate already approved")

    booking.status = models.BookingStatus.cancelled
    booking.completed_at = datetime.utcnow()

    # ✅ ₹100 visiting charge bill
    garage = db.query(models.Garage).filter(models.Garage.id == booking.garage_id).first()
    if garage:
        _generate_visiting_charge_bill(booking, garage, db)

    db.commit()
    db.refresh(booking)

    return {
        "message": "Additional estimate rejected. ₹100 visiting charge applicable.",
        "booking_id": booking_id,
        "status": "cancelled",
        "visiting_charge": 100,
        "bill_note": "Mechanic ko ₹100 cash/UPI de dena."
    }


# ──────────────────────────────────────────
# GET BILL
# ──────────────────────────────────────────

@router.get("/{booking_slug_or_id}/bill", response_model=schemas.BillResponse)
def get_booking_bill(
    booking_slug_or_id: str,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    booking = _resolve_booking(booking_slug_or_id, db)
    if not booking or booking.customer_id != current_customer.id:
        raise HTTPException(status_code=404, detail="Booking not found")

    bill = db.query(models.Bill).filter(models.Bill.booking_id == booking.id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found. Payment may not have been marked as paid yet.")

    return bill
