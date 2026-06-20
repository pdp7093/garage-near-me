from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from datetime import datetime
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from pydantic import BaseModel
import os, math, random, secrets, string

import models, schemas
from database import get_db
from routers.websocket_manager import ws_manager
from routers.auth import send_whatsapp_otp

# ── Firebase FCM ──────────────────────────
import firebase_admin
from firebase_admin import credentials, messaging as fcm_messaging

_FCM_INITIALIZED = False
def _init_fcm():
    global _FCM_INITIALIZED
    if _FCM_INITIALIZED:
        return
    try:
        sa_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "firebase-service-account.json"))
        if os.path.isfile(sa_path):
            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(sa_path))
            _FCM_INITIALIZED = True
            print("✅ Firebase FCM initialized")
        else:
            print(f"⚠️  firebase-service-account.json not found at: {sa_path}")
    except Exception as e:
        print(f"⚠️  Firebase init error: {e}")

_init_fcm()

async def send_fcm_multicast(tokens: list, title: str, body: str, data: dict = None):
    if not _FCM_INITIALIZED or not tokens:
        return 0
    try:
        msg = fcm_messaging.MulticastMessage(
            notification=fcm_messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            tokens=tokens,
            android=fcm_messaging.AndroidConfig(priority="high"),
        )
        resp = fcm_messaging.send_each_for_multicast(msg)
        print(f"✅ FCM: {resp.success_count}/{len(tokens)} delivered")
        return resp.success_count
    except Exception as e:
        print(f"⚠️  FCM multicast error: {e}")
        return 0

router = APIRouter()

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM  = os.getenv("ALGORITHM", "HS256")

customer_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
garage_oauth2   = OAuth2PasswordBearer(tokenUrl="/api/garage/login")


# ──────────────────────────────────────────
# AUTH HELPERS
# ──────────────────────────────────────────

def get_current_customer(token: str = Depends(customer_oauth2), db: Session = Depends(get_db)) -> models.Customer:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "customer":
            raise HTTPException(status_code=403, detail="Not a customer token")
        customer = db.query(models.Customer).filter(models.Customer.id == payload.get("user_id")).first()
        if not customer:
            raise HTTPException(status_code=401, detail="Customer not found")
        return customer
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_garage(token: str = Depends(garage_oauth2), db: Session = Depends(get_db)) -> models.Garage:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "garage":
            raise HTTPException(status_code=403, detail="Not a garage token")
        garage = db.query(models.Garage).filter(models.Garage.id == payload.get("user_id")).first()
        if not garage:
            raise HTTPException(status_code=401, detail="Garage not found")
        return garage
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ──────────────────────────────────────────
# HAVERSINE
# ──────────────────────────────────────────

def haversine(lat1, lng1, lat2, lng2):
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = math.sin(d_lat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def _resolve_sos(sos_id: str, db) -> models.SOS:
    """Slug ya integer ID se SOS lookup karo."""
    if sos_id.isdigit():
        return db.query(models.SOS).filter(models.SOS.id == int(sos_id)).first()
    return db.query(models.SOS).filter(models.SOS.slug == sos_id).first()


# ──────────────────────────────────────────
# SCHEMAS
# ──────────────────────────────────────────

class SOSCreateRequest(BaseModel):
    lat:              float
    lng:              float
    address:          Optional[str] = None
    vehicle_type:     Optional[str] = None
    vehicle_number:   Optional[str] = None
    vehicle_model:    Optional[str] = None
    description:      Optional[str] = None
    radius_km:        float = 2.0

class SOSEstimatePayload(BaseModel):
    estimated_amount: float
    description:      Optional[str] = None
    visiting_charge:  Optional[float] = None
    estimate_details: Optional[list] = None


# ──────────────────────────────────────────
# 1. CUSTOMER — CREATE SOS
# POST /api/sos/create
# ──────────────────────────────────────────

@router.post("/create")
async def create_sos(
    data: SOSCreateRequest,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    Customer SOS trigger karta hai.
    2km radius ke sabhi active + SOS-available garages ko broadcast hoga.
    """
    # Radius mein SOS-available garages dhundho
    garages = (
        db.query(models.Garage)
        .join(models.GarageLocation)
        .filter(
            models.Garage.is_active       == True,
            models.Garage.is_verified     == True,
            models.Garage.is_sos_available == True,
            models.GarageLocation.latitude  != None,
            models.GarageLocation.longitude != None,
        )
        .all()
    )

    nearby_garages = []
    for g in garages:
        loc = g.location
        dist = haversine(data.lat, data.lng, loc.latitude, loc.longitude)
        if dist <= data.radius_km:
            nearby_garages.append({ "id": g.id, "name": g.name, "distance_km": round(dist, 2) })

    if not nearby_garages:
        # Radius badha ke try karo
        for g in garages:
            loc = g.location
            dist = haversine(data.lat, data.lng, loc.latitude, loc.longitude)
            if dist <= 10.0:
                nearby_garages.append({ "id": g.id, "name": g.name, "distance_km": round(dist, 2) })

    # SOS request create karo — dedicated SOS table mein
    sos_request = models.SOS(
        customer_id             = current_customer.id,
        garage_id               = None,  # Blast notification to all, not just first
        vehicle_type            = data.vehicle_type or "unknown",
        vehicle_model           = data.vehicle_model,
        vehicle_number          = data.vehicle_number,
        description             = data.description,
        latitude                = data.lat,
        longitude               = data.lng,
        address                 = data.address,
        status                  = models.SOSStatus.broadcasting,
        broadcast_radius_km     = data.radius_km,
        estimate_status         = models.EstimateStatus.not_required,
    ) if nearby_garages else None

    if not sos_request:
        return {
            "success": False,
            "message": "Koi SOS-available garage nahi mila aas paas mein.",
            "nearby_garages": [],
            "sos_id": None
        }

    db.add(sos_request)
    db.commit()
    db.refresh(sos_request)

    # Random slug generate karo (koi ID visible nahi)
    chars = string.ascii_lowercase + string.digits
    while True:
        candidate = ''.join(secrets.choice(chars) for _ in range(10))
        if not db.query(models.SOS).filter(models.SOS.slug == candidate).first():
            break
    sos_request.sos_number = f"SOS-{sos_request.id}"
    sos_request.slug       = candidate
    db.commit()
    db.refresh(sos_request)

    # WebSocket + FCM broadcast — nearby garages ko notification
    nearby_garage_ids = [g["id"] for g in nearby_garages]
    vt_label = "2 Wheeler" if data.vehicle_type == "two_wheeler" else "4 Wheeler" if data.vehicle_type == "four_wheeler" else data.vehicle_type or "Vehicle"

    notif_title = f"🆘 Emergency SOS — {vt_label} Breakdown"
    notif_body  = "A vehicle needs immediate assistance nearby. Open the app to respond."

    # WebSocket (foreground mechanics)
    await ws_manager.broadcast_to_garages(nearby_garage_ids, {
        "type":   "sos_alert",
        "sos_id": sos_request.id,
        "slug":   sos_request.slug,
        "title":  notif_title,
        "body":   notif_body,
        "screen": "sos-alerts",
    })

    # FCM (background mechanics) — sirf ek baar, create pe only
    nearby_garage_objs = [g for g in garages if g.id in nearby_garage_ids]
    fcm_tokens = [g.fcm_token for g in nearby_garage_objs if g.fcm_token]
    if fcm_tokens:
        import asyncio
        asyncio.create_task(send_fcm_multicast(
            tokens=fcm_tokens,
            title=notif_title,
            body=notif_body,
            data={
                "type":   "sos_alert",
                "sos_id": str(sos_request.id),
                "slug":   sos_request.slug or "",
                "screen": "sos-alerts",
            }
        ))

    print(f"\n{'='*50}")
    print(f"SOS BROADCAST — SOS #{sos_request.id} ({sos_request.sos_number})")
    print(f"Customer: {current_customer.name} ({current_customer.phone})")
    print(f"Location: {data.lat}, {data.lng}")
    print(f"WS notified: {[g['name'] for g in nearby_garages]}")
    print(f"FCM tokens: {len(fcm_tokens)}")
    print(f"{'='*50}\n")

    return {
        "success":        True,
        "sos_id":         sos_request.id,
        "sos_slug":       sos_request.slug,
        "nearby_garages": nearby_garages,
        "message":        f"{len(nearby_garages)} garages ko alert bheja gaya!"
    }


# ──────────────────────────────────────────
# 2. GARAGE — GET ACTIVE SOS ALERTS
# GET /api/sos/active
# ──────────────────────────────────────────

@router.get("/active")
def get_active_sos(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage ke liye active (broadcasting/accepted) SOS requests.
    Garage ki location ke 2km radius mein.
    """
    loc = current_garage.location
    if not loc or not loc.latitude or not loc.longitude:
        return []

    # Pending/Broadcasting/Accepted SOS requests for this garage
    active_garage_statuses = [models.SOSStatus.accepted, models.SOSStatus.on_the_way, models.SOSStatus.in_progress]
    sos_requests = db.query(models.SOS).filter(
        or_(
            models.SOS.status == models.SOSStatus.broadcasting,
            (models.SOS.status.in_(active_garage_statuses)) & (models.SOS.garage_id == current_garage.id)
        )
    ).order_by(models.SOS.created_at.desc()).all()

    results = []
    for s in sos_requests:
        if s.latitude and s.longitude:
            dist = haversine(loc.latitude, loc.longitude, s.latitude, s.longitude)
        else:
            dist = None

        # Time ago
        now      = datetime.utcnow()
        diff     = now - s.created_at.replace(tzinfo=None)
        mins     = int(diff.total_seconds() / 60)
        time_ago = f"{mins} min ago" if mins < 60 else f"{int(mins/60)}h ago"

        results.append({
            "id":              s.id,
            "slug":            s.slug,
            "sos_number":      s.sos_number,
            "customer_id":     s.customer_id,
            "vehicle_type":    s.vehicle_type,
            "vehicle_model":   s.vehicle_model,
            "vehicle_number":  s.vehicle_number,
            "description":     s.description,
            "latitude":        s.latitude,
            "longitude":       s.longitude,
            "address":         s.address,
            "distance_km":     round(dist, 2) if dist else None,
            "time_ago":        time_ago,
            "status":          s.status.value,
            "created_at":      s.created_at.isoformat(),
        })

    return results


# ──────────────────────────────────────────
# 3. GARAGE — GET SOS DETAIL
# GET /api/sos/{booking_id}
# ──────────────────────────────────────────

@router.get("/{sos_id}")
def get_sos_detail(
    sos_id: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request or sos_request.garage_id != current_garage.id:
        raise HTTPException(status_code=404, detail="SOS request not found")

    loc  = current_garage.location
    dist = None
    if loc and loc.latitude and sos_request.latitude:
        dist = haversine(loc.latitude, loc.longitude, sos_request.latitude, sos_request.longitude)

    now      = datetime.utcnow()
    diff     = now - sos_request.created_at.replace(tzinfo=None)
    mins     = int(diff.total_seconds() / 60)
    time_ago = f"{mins} min ago" if mins < 60 else f"{int(mins/60)}h ago"

    customer = db.query(models.Customer).filter(models.Customer.id == sos_request.customer_id).first()

    return {
        "id":               sos_request.id,
        "slug":             sos_request.slug,
        "sos_number":       sos_request.sos_number,
        "status":           sos_request.status.value,
        "customer_id":      sos_request.customer_id,
        "customer_name":    customer.name if customer else None,
        "garage_name":      current_garage.name,
        "garage_address":   current_garage.location.address if current_garage.location and hasattr(current_garage.location, 'address') else None,
        "vehicle_type":     sos_request.vehicle_type,
        "vehicle_model":    sos_request.vehicle_model,
        "vehicle_number":   sos_request.vehicle_number,
        "description":      sos_request.description,
        "latitude":         sos_request.latitude,
        "longitude":        sos_request.longitude,
        "address":          sos_request.address,
        "distance_km":      round(dist, 2) if dist else None,
        "time_ago":         time_ago,
        "estimated_charge": float(sos_request.estimated_charge) if sos_request.estimated_charge else None,
        "final_charge":     float(sos_request.final_charge) if sos_request.final_charge else None,
        "visiting_charge":  float(sos_request.visiting_charge) if hasattr(sos_request, 'visiting_charge') and sos_request.visiting_charge else None,
        "estimate_status":  sos_request.estimate_status.value,
        "estimate_details": sos_request.estimate_details,
        "garage_note":      sos_request.garage_note,
        "responded_at":     sos_request.responded_at.isoformat() if sos_request.responded_at else None,
        "arrived_at":       sos_request.arrived_at.isoformat() if sos_request.arrived_at else None,
        "started_at":       sos_request.started_at.isoformat() if sos_request.started_at else None,
        "completed_at":     sos_request.completed_at.isoformat() if sos_request.completed_at else None,
        "created_at":       sos_request.created_at.isoformat(),
    }


# ──────────────────────────────────────────
# 4. GARAGE — ACCEPT SOS
# POST /api/sos/{booking_id}/accept
# ──────────────────────────────────────────

@router.post("/{sos_id}/accept")
def accept_sos(
    sos_id: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request or sos_request.status != models.SOSStatus.broadcasting:
        raise HTTPException(status_code=404, detail="SOS not found or already taken")

    sos_request.garage_id    = current_garage.id
    sos_request.status       = models.SOSStatus.accepted
    sos_request.responded_at = datetime.utcnow()
    sos_request.accepted_at  = datetime.utcnow()
    db.commit()
    db.refresh(sos_request)

    print(f"\n✅ SOS #{sos_request.id} accepted by Garage #{current_garage.id} — {current_garage.name}")

    return {"message": "SOS accepted!", "sos_id": sos_request.id, "slug": sos_request.slug, "status": "accepted"}


# ──────────────────────────────────────────
# 5. GARAGE — REJECT SOS
# POST /api/sos/{booking_id}/reject
# ──────────────────────────────────────────

@router.post("/{sos_id}/reject")
def reject_sos(
    sos_id: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request or sos_request.status != models.SOSStatus.broadcasting:
        raise HTTPException(status_code=404, detail="SOS not found")

    # Locally reject for this garage only (frontend will hide it)
    # Status remains broadcasting for other garages
    return { "message": "SOS rejected locally", "sos_id": sos_request.id }


# ──────────────────────────────────────────
# 6. GARAGE — SEND SOS ESTIMATE
# PATCH /api/sos/{booking_id}/estimate
# ──────────────────────────────────────────

@router.patch("/{sos_id}/estimate")
def send_sos_estimate(
    sos_id: str,
    payload: SOSEstimatePayload,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request or sos_request.garage_id != current_garage.id or sos_request.status != models.SOSStatus.accepted:
        raise HTTPException(status_code=404, detail="SOS request not found or not accepted")

    sos_request.estimated_charge = payload.estimated_amount
    sos_request.garage_note      = payload.description
    sos_request.visiting_charge  = payload.visiting_charge
    sos_request.estimate_details = payload.estimate_details
    sos_request.estimate_status  = models.EstimateStatus.pending

    # OTP generate karo
    otp = str(random.randint(100000, 999999))
    sos_request.estimate_otp          = otp
    sos_request.estimate_otp_verified = False
    sos_request.estimate_otp_sent_at  = datetime.utcnow()

    db.commit()
    db.refresh(sos_request)

    # TODO: SMS customer ko
    print(f"\n📋 SOS Estimate sent — SOS #{sos_id}")
    print(f"Amount: ₹{payload.estimated_amount}")
    print(f"Customer OTP: {otp}")
    print(f"{'='*40}\n")

    # ✅ WhatsApp OTP customer ko bhejo
    customer = db.query(models.Customer).filter(
        models.Customer.id == sos_request.customer_id
    ).first()
    if customer and customer.phone:
        import asyncio
        asyncio.create_task(
            send_whatsapp_otp(customer.phone, otp)
        )

    return {
        "message":          "Estimate sent! OTP generated.",
        "estimated_amount": payload.estimated_amount,
        "otp":              otp  # TESTING ONLY
    }


# ──────────────────────────────────────────
# 7. GARAGE — VERIFY OTP → START WORK
# POST /api/sos/{booking_id}/verify-otp
# ──────────────────────────────────────────

@router.post("/{sos_id}/verify-otp")
def verify_sos_otp(
    sos_id: str,
    otp: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request or sos_request.garage_id != current_garage.id:
        raise HTTPException(status_code=404, detail="SOS request not found")
    if sos_request.estimate_otp != otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    if sos_request.estimate_otp_verified:
        raise HTTPException(status_code=400, detail="OTP already used")

    sos_request.estimate_otp_verified = True
    sos_request.estimate_status       = models.EstimateStatus.approved
    sos_request.status                = models.SOSStatus.in_progress
    sos_request.started_at            = datetime.utcnow()
    db.commit()

    return { "message": "OTP verified! Kaam shuru karo.", "status": "in_progress" }


# ──────────────────────────────────────────
# 8. GARAGE — COMPLETE SOS
# POST /api/sos/{booking_id}/complete
# ──────────────────────────────────────────

# ──────────────────────────────────────────
# GARAGE — MARK ARRIVED
# PATCH /api/sos/{sos_id}/mark-arrived
# ──────────────────────────────────────────

@router.post("/{sos_id}/mark-arrived")
def mark_arrived(
    sos_id: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request or sos_request.garage_id != current_garage.id:
        raise HTTPException(status_code=404, detail="SOS not found or not in accepted state")
    if sos_request.status != models.SOSStatus.accepted:
        raise HTTPException(status_code=400, detail="SOS not in accepted state")

    sos_request.arrived_at = datetime.utcnow()
    # Status 'accepted' hi rehega — frontend arrived_at check karta hai
    db.commit()
    db.refresh(sos_request)

    return {"message": "Arrived marked!", "arrived_at": sos_request.arrived_at.isoformat()}


@router.post("/{sos_id}/complete")
def complete_sos(
    sos_id: str,
    final_amount: float,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request:
        raise HTTPException(status_code=404, detail="SOS not found")
    if sos_request.garage_id != current_garage.id:
        raise HTTPException(status_code=403, detail="Not your SOS")
    if sos_request.status not in [models.SOSStatus.accepted, models.SOSStatus.in_progress]:
        raise HTTPException(status_code=400, detail="SOS not in acceptable state to complete")

    sos_request.status       = models.SOSStatus.completed
    sos_request.final_charge = final_amount
    sos_request.completed_at = datetime.utcnow()

    # Calculate platform commission
    final_charge_float = float(final_amount)
    commission_rule = db.query(models.CommissionRule).filter(
        models.CommissionRule.is_active == True,
        models.CommissionRule.min_amount <= final_charge_float,
        (models.CommissionRule.max_amount >= final_charge_float) | (models.CommissionRule.max_amount == None)
    ).first()

    platform_commission = 0.0
    if commission_rule:
        platform_commission = (final_charge_float * float(commission_rule.percentage)) / 100.0

    garage_earnings = final_charge_float - platform_commission

    sos_request.platform_commission = platform_commission
    sos_request.garage_earnings = garage_earnings

    if current_garage.pending_platform_dues is None:
        current_garage.pending_platform_dues = 0.0
    current_garage.pending_platform_dues = float(current_garage.pending_platform_dues) + float(platform_commission)

    if not current_garage.has_completed_trial and current_garage.pending_platform_dues >= 500.0:
        current_garage.is_credit_locked = True

    db.commit()

    return {"message": "SOS completed!", "final_amount": final_amount, "slug": sos_request.slug}


# ──────────────────────────────────────────
# 9. GARAGE — SOS HISTORY
# GET /api/sos/history
# ──────────────────────────────────────────

@router.get("/history/all")
def get_sos_history(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    sos_requests = db.query(models.SOS).filter(
        models.SOS.garage_id    == current_garage.id,
        models.SOS.status.in_([
            models.SOSStatus.completed,
            models.SOSStatus.cancelled,
        ])
    ).order_by(models.SOS.created_at.desc()).all()

    return [{
        "id":              s.id,
        "sos_number":      s.sos_number,
        "status":          s.status.value,
        "vehicle_type":    s.vehicle_type,
        "vehicle_model":   s.vehicle_model,
        "vehicle_number":  s.vehicle_number,
        "description":     s.description,
        "address":         s.address,
        "final_charge":    float(s.final_charge) if s.final_charge else None,
        "platform_commission": float(s.platform_commission) if s.platform_commission else None,
        "garage_earnings": float(s.garage_earnings) if s.garage_earnings else None,
        "created_at":      s.created_at.isoformat(),
        "completed_at":    s.completed_at.isoformat() if s.completed_at else None,
    } for s in sos_requests]


# ──────────────────────────────────────────
# 10. CUSTOMER — GET SOS STATUS
# GET /api/sos/customer/{booking_id}
# ──────────────────────────────────────────

@router.get("/customer/history")
def get_customer_sos_history(
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """
    Customer ke saari SOS requests (active + completed + cancelled)
    GET /api/sos/customer/history
    """
    sos_requests = db.query(models.SOS).filter(
        models.SOS.customer_id == current_customer.id
    ).order_by(models.SOS.created_at.desc()).all()

    result = []
    for sos in sos_requests:
        garage = sos.garage
        dist = None
        if garage and garage.location and garage.location.latitude and sos.latitude:
            dist = haversine(
                garage.location.latitude, garage.location.longitude,
                sos.latitude, sos.longitude
            )

        result.append({
            "id": sos.id,
            "sos_number": sos.sos_number,
            "slug": sos.slug,
            "status": sos.status.value,
            "garage_name": garage.name if garage else None,
            "distance_km": round(dist, 2) if dist else None,
            "estimated_charge": float(sos.estimated_charge) if sos.estimated_charge else None,
            "estimate_status": sos.estimate_status.value,
            "final_charge": float(sos.final_charge) if sos.final_charge else None,
            "vehicle_type": sos.vehicle_type,
            "vehicle_model": sos.vehicle_model,
            "vehicle_number": sos.vehicle_number,
            "description": sos.description,
            "address": sos.address,
            "responded_at": sos.responded_at.isoformat() if sos.responded_at else None,
            "started_at": sos.started_at.isoformat() if sos.started_at else None,
            "completed_at": sos.completed_at.isoformat() if sos.completed_at else None,
            "created_at": sos.created_at.isoformat(),
            "estimate_details": sos.estimate_details,
        })

    return result


@router.get("/customer/{sos_id}")
def get_sos_status_customer(
    sos_id: str,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    q = db.query(models.SOS).filter(models.SOS.customer_id == current_customer.id)
    if sos_id.isdigit():
        sos_request = q.filter(models.SOS.id == int(sos_id)).first()
    else:
        sos_request = q.filter(models.SOS.slug == sos_id).first()
    if not sos_request:
        raise HTTPException(status_code=404, detail="SOS request not found")

    garage = sos_request.garage

    # Distance calculate karo agar location available hai
    dist = None
    if garage and garage.location and garage.location.latitude and sos_request.latitude:
        dist = haversine(
            garage.location.latitude, garage.location.longitude,
            sos_request.latitude, sos_request.longitude
        )

    return {
        "id":               sos_request.id,
        "sos_number":       sos_request.sos_number,
        "status":           sos_request.status.value,
        "garage_name":      garage.name if garage else None,
        "distance_km":      round(dist, 2) if dist else None,
        "estimated_charge": float(sos_request.estimated_charge) if sos_request.estimated_charge else None,
        "estimate_status":  sos_request.estimate_status.value,
        "final_charge":     float(sos_request.final_charge) if sos_request.final_charge else None,
        "vehicle_type":     sos_request.vehicle_type,
        "vehicle_model":    sos_request.vehicle_model,
        "vehicle_number":   sos_request.vehicle_number,
        "description":      sos_request.description,
        "responded_at":     sos_request.responded_at.isoformat() if sos_request.responded_at else None,
        "started_at":       sos_request.started_at.isoformat() if sos_request.started_at else None,
        "completed_at":     sos_request.completed_at.isoformat() if sos_request.completed_at else None,
        "created_at":       sos_request.created_at.isoformat(),
        "estimate_details": sos_request.estimate_details,
    }


# ──────────────────────────────────────────
# CUSTOMER — REBROADCAST SOS (repeat WS blast)
# POST /api/sos/customer/{sos_id}/rebroadcast
# ──────────────────────────────────────────

@router.post("/customer/{sos_id}/rebroadcast")
async def rebroadcast_sos(
    sos_id: str,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    sos_request = _resolve_sos(sos_id, db)
    if not sos_request:
        raise HTTPException(status_code=404, detail="SOS not found")

    # Sirf broadcasting status mein hi rebroadcast karo
    if sos_request.status != models.SOSStatus.broadcasting:
        return {"rebroadcast": False, "reason": "SOS not broadcasting"}

    # Sirf customer apna hi SOS rebroadcast kar sakta hai
    if sos_request.customer_id != current_customer.id:
        raise HTTPException(status_code=403, detail="Not your SOS")

    # Nearby garages dhundho (same logic)
    garages = (
        db.query(models.Garage)
        .join(models.GarageLocation)
        .filter(
            models.Garage.is_active        == True,
            models.Garage.is_verified      == True,
            models.Garage.is_sos_available == True,
            models.GarageLocation.latitude  != None,
            models.GarageLocation.longitude != None,
        )
        .all()
    )

    radius = sos_request.broadcast_radius_km or 2.0
    nearby_ids = []
    for g in garages:
        loc = g.location
        if not loc: continue
        dist = haversine(sos_request.latitude, sos_request.longitude, loc.latitude, loc.longitude)
        if dist <= radius:
            nearby_ids.append(g.id)

    if not nearby_ids:
        return {"rebroadcast": False, "reason": "No nearby garages"}

    vt = sos_request.vehicle_type or "Vehicle"
    vt_label = "2 Wheeler" if vt == "two_wheeler" else "4 Wheeler" if vt == "four_wheeler" else vt

    # Sirf WebSocket — FCM repeat nahi karna (ek baar pehle ja chuka)
    await ws_manager.broadcast_to_garages(nearby_ids, {
        "type":   "sos_alert",
        "sos_id": sos_request.id,
        "slug":   sos_request.slug,
        "title":  f"🆘 Emergency SOS — {vt_label} Breakdown",
        "body":   "A vehicle needs immediate assistance nearby. Open the app to respond.",
        "screen": "sos-alerts",
    })

    return {"rebroadcast": True, "garages_notified": len(nearby_ids)}


# ──────────────────────────────────────────
# 11. CUSTOMER — CANCEL SOS
# POST /api/sos/customer/{sos_id}/cancel
# ──────────────────────────────────────────

@router.post("/customer/{sos_id}/cancel")
def cancel_sos_customer(
    sos_id: str,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    q = db.query(models.SOS).filter(
        models.SOS.customer_id == current_customer.id,
        models.SOS.status.notin_([models.SOSStatus.completed, models.SOSStatus.cancelled])
    )
    if sos_id.isdigit():
        sos_request = q.filter(models.SOS.id == int(sos_id)).first()
    else:
        sos_request = q.filter(models.SOS.slug == sos_id).first()
    if not sos_request:
        raise HTTPException(status_code=404, detail="SOS request not found or cannot be cancelled")

    sos_request.status       = models.SOSStatus.cancelled
    sos_request.cancelled_at = datetime.utcnow()
    db.commit()
    db.refresh(sos_request)

    return {"message": "SOS cancelled", "status": sos_request.status.value}


# ──────────────────────────────────────────
# 11b. CUSTOMER — GET ACTIVE SOS
# GET /api/sos/customer/active
# ──────────────────────────────────────────

@router.get("/customer/active")
def get_customer_active_sos(
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    active_statuses = [
        models.SOSStatus.broadcasting,
        models.SOSStatus.accepted,
        models.SOSStatus.on_the_way,
        models.SOSStatus.in_progress
    ]
    
    active_sos = db.query(models.SOS).filter(
        models.SOS.customer_id == current_customer.id,
        models.SOS.status.in_(active_statuses)
    ).order_by(models.SOS.created_at.desc()).first()
    
    if active_sos:
        return {
            "has_active": True,
            "sos_id": active_sos.id,
            "sos_slug": active_sos.slug if hasattr(active_sos, 'slug') else active_sos.id,
            "status": active_sos.status.value
        }
    return {"has_active": False}