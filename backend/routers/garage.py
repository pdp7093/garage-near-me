from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from sqlalchemy import Date, cast, func
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os, re, unicodedata
from fastapi import UploadFile, File, Form
import models, schemas
from database import get_db
from utils.file_upload import delete_uploaded_file, save_garage_document, save_garage_logo
import math
from fastapi.responses import JSONResponse
from datetime import datetime as dt
from typing import Optional as Opt
from routers.admin_auth import get_current_admin


def _make_slug(name: str, garage_id: int) -> str:
    """Garage name + ID se clean URL slug banao."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return f"{s}-{garage_id}"


def _make_service_slug(name: str, service_id: int) -> str:
    """Service name + ID se clean URL slug banao."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return f"{s}-{service_id}"


def _make_booking_slug(booking_number: str, booking_id: int) -> str:
    """Booking number + ID se clean URL slug banao."""
    s = unicodedata.normalize("NFKD", booking_number).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return f"{s}-{booking_id}"

router = APIRouter()

SECRET_KEY                  = os.getenv("SECRET_KEY", "supersecretkey_gnm_12345")
ALGORITHM                   = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# garage_auth.py se token aata hai — same tokenUrl
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/garage-auth/verify-otp")


# ──────────────────────────────────────────
# GET CURRENT GARAGE (JWT se)
# ──────────────────────────────────────────

def get_current_garage(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.Garage:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        garage_id: int = payload.get("user_id")
        role: str      = payload.get("role")
        if garage_id is None or role != "garage":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    garage = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if garage is None:
        raise credentials_exception
    return garage



@router.get("/me", response_model=schemas.GarageResponse)
def get_my_profile(current_garage: models.Garage = Depends(get_current_garage)):
    """
    JWT token se apna poora profile fetch karo.
    Dashboard load hote waqt yahi call hoga.
    """
    return current_garage


@router.post("/me/logo", response_model=schemas.GarageResponse)
def upload_my_logo(
    logo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    filename = logo.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    content_type = (logo.content_type or "").lower()

    if not content_type.startswith("image/") and extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Please upload a valid image file."
        )

    old_logo_url = current_garage.logo_url
    logo_url = save_garage_logo(logo, current_garage.id)

    current_garage.logo_url = logo_url
    db.commit()
    db.refresh(current_garage)

    delete_uploaded_file(old_logo_url)
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
        category     = service_data.category,
        price        = service_data.price,
        price_type   = service_data.price_type,
        is_available = service_data.is_available,
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    
    # Now generate slug with service ID
    service.slug = _make_service_slug(service.service_name, service.id)
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

# ──────────────────────────────────────────
# 10. PUBLIC SEARCH GARAGES
# GET /api/garage/search
# ──────────────────────────────────────────

@router.get("/search", response_model=list[schemas.GaragePublicResponse])
def search_garages(
    city: str = "Ahmedabad",
    vehicle_type: str = None, # four_wheeler | two_wheeler | both
    is_sos: bool = False,
    db: Session = Depends(get_db)
):
    """
    Customer search page ke liye API.
    Only verified and active garages return honge.
    """
    query = db.query(models.Garage).filter(
        models.Garage.is_active == True,
        models.Garage.is_verified == True,
        models.Garage.is_credit_locked == False
    )

    if vehicle_type:
        query = query.filter(
            (models.Garage.garage_type == vehicle_type) | 
            (models.Garage.garage_type == "both")
        )

    if is_sos:
        query = query.filter(models.Garage.is_sos_available == True)

    query = query.join(models.GarageLocation).filter(models.GarageLocation.city.ilike(f"%{city}%"))

    return query.all()


# ──────────────────────────────────────────
# 11. GET MY DOCUMENTS
# GET /api/garage/me/documents
# ──────────────────────────────────────────

@router.get("/me/documents", response_model=list[schemas.GarageDocumentResponse])
def get_my_documents(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    return db.query(models.GarageDocument).filter(
        models.GarageDocument.garage_id == current_garage.id
    ).all()


#  Upload Garage Document
# ──────────────────────────────────────────
# UPLOAD GARAGE DOCUMENT
# POST /api/garage/me/documents
# ──────────────────────────────────────────

@router.post("/me/documents")
def upload_garage_document(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    file_url = save_garage_document(
        file,
        document_type=document_type,
        garage_name=current_garage.name,
        owner_name=current_garage.owner_name,
    )

    # Save DB record
    document = models.GarageDocument(
        garage_id=current_garage.id,
        document_type=document_type,
        file_url=file_url
    )

    db.add(document)
    db.commit()
    db.refresh(document)

    return {
        "message": "Document uploaded successfully",
        "document": document
    }



# All Garage
# garage.py mein add karo (end mein)

@router.get("/admin/all", response_model=list[schemas.GarageResponse])
def get_all_garages_admin(
    current_admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin — saare garages fetch karo (active + inactive dono)"""
    return db.query(models.Garage).order_by(models.Garage.created_at.desc()).all()

# Admin : Get single garage by slug
@router.get("/admin/slug/{slug}", response_model=schemas.GarageResponse)
def get_garage_by_slug_admin(slug: str, current_admin: models.Admin = Depends(get_current_admin), db: Session = Depends(get_db)):
    g = db.query(models.Garage).filter(models.Garage.slug == slug).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garage not found")
    return g

# Admin : Get single garage by ID
@router.get("/admin/{garage_id}", response_model=schemas.GarageResponse)
def get_garage_by_id_admin(garage_id:int, current_admin: models.Admin = Depends(get_current_admin), db:Session = Depends(get_db)):
    g = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garage not found")
    return g


# ── ADMIN: Toggle status
@router.patch("/admin/{garage_id}/toggle-status", response_model=schemas.GarageResponse)
def toggle_garage_status(
    garage_id: int,
    data: schemas.GarageUpdate,
    current_admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    g = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garage not found")
    g.is_active = data.is_active
    db.commit()
    db.refresh(g)
    return g

# ── ADMIN: Delete garage
@router.delete("/admin/{garage_id}", status_code=204)
def delete_garage_admin(
    garage_id: int,
    current_admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    g = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garage not found")
    db.delete(g)
    db.commit()
    return None

# ──────────────────────────────────────────
# DASHBOARD SUMMARY
# GET /api/garage/dashboard-summary
# ──────────────────────────────────────────

@router.get("/dashboard-summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage Dashboard Summary
    """

    # ─────────────────────────────
    # SERVICES COUNT
    # ─────────────────────────────

    services_count = db.query(
        models.GarageService
    ).filter(
        models.GarageService.garage_id == current_garage.id
    ).count()


    # ─────────────────────────────
    # DOCUMENTS COUNT
    # ─────────────────────────────

    documents_count = db.query(
        models.GarageDocument
    ).filter(
        models.GarageDocument.garage_id == current_garage.id
    ).count()


    # ─────────────────────────────
    # WORKING DAYS COUNT
    # ─────────────────────────────

    working_days = db.query(
        models.GarageWorkingHours
    ).filter(
        models.GarageWorkingHours.garage_id == current_garage.id,
        models.GarageWorkingHours.is_open == True
    ).count()


    # ─────────────────────────────
    # PROFILE COMPLETION
    # ─────────────────────────────

    total_fields = 8
    completed = 0

    if current_garage.name:
        completed += 1

    if current_garage.owner_name:
        completed += 1

    if current_garage.phone:
        completed += 1

    if current_garage.email:
        completed += 1

    if current_garage.garage_type:
        completed += 1

    if current_garage.location:
        completed += 1

    if services_count > 0:
        completed += 1

    if documents_count > 0:
        completed += 1

    profile_completion = int(
        (completed / total_fields) * 100
    )


    # ─────────────────────────────
    # BOOKING METRICS
    # ─────────────────────────────

    today = datetime.utcnow().date()

    booking_earnings = db.query(
        func.coalesce(func.sum(models.Booking.final_amount), 0)
    ).filter(
        models.Booking.garage_id == current_garage.id,
        models.Booking.status == models.BookingStatus.completed,
        cast(models.Booking.completed_at, Date) == today
    ).scalar() or 0

    sos_earnings = db.query(
        func.coalesce(func.sum(models.SOS.final_charge), 0)
    ).filter(
        models.SOS.garage_id == current_garage.id,
        models.SOS.status == models.SOSStatus.completed,
        cast(models.SOS.completed_at, Date) == today
    ).scalar() or 0

    todays_earnings = float(booking_earnings) + float(sos_earnings)

    jobs_completed = db.query(models.Booking).filter(
        models.Booking.garage_id == current_garage.id,
        models.Booking.status == models.BookingStatus.completed
    ).count()

    sos_completed = db.query(models.SOS).filter(
        models.SOS.garage_id == current_garage.id,
        models.SOS.status == models.SOSStatus.completed
    ).count()

    # Rating model abhi codebase mein nahi hai, isliye fake rating return nahi karte.
    customer_rating = None


    # ─────────────────────────────
    # RESPONSE
    # ─────────────────────────────

    return {

        "garage_name": current_garage.name,

        "city": (
            current_garage.location.city
            if current_garage.location
            else None
        ),

        # Business Metrics
        "todays_earnings": float(todays_earnings),
        "jobs_completed": jobs_completed,
        "sos_completed": sos_completed,
        "customer_rating": customer_rating,

        # Setup Metrics
        "services_count": services_count,
        "documents_count": documents_count,
        "working_days": working_days,
        "profile_completion": profile_completion,

        # Status
        "is_sos_available": current_garage.is_sos_available
    }

# ---------------------------------------
# Get My Services
# ---------------------------------------

@router.get("/me/services",response_model=list[schemas.GarageServiceResponse])
def get_my_services(db:Session = Depends(get_db), current_garage: models.Garage = Depends(get_current_garage)):
    """ Garage Services """
    return db.query(models.GarageService).filter(
        models.GarageService.garage_id == current_garage.id
    ).order_by(models.GarageService.id.desc()).all()


# ----- Update Service --------
@router.patch("/me/services/{service_id}",response_model = schemas.GarageServiceResponse)
def update_service(service_id: int , service_data: schemas.GarageServiceCreate,
    db:Session = Depends(get_db), current_garage:models.Garage = Depends(get_current_garage)):

    """ Update """

    service = db.query(models.GarageService).filter(
        models.GarageService.id == service_id ,
        models.GarageService.garage_id == current_garage.id
    ).first()

    if not service:
        raise HTTPException(status_code = 404, detail = "Service Not Found")

    for field, value in service_data.model_dump().items():
        setattr(service, field,value)

    db.commit()
    db.refresh(service)

    return service

# ──────────────────────────────────────────
# TOGGLE SERVICE STATUS
# PATCH /api/garage/me/services/{service_id}/toggle
# ──────────────────────────────────────────

@router.patch("/me/services/{service_id}/toggle")
def toggle_service_status(
    service_id: int,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):

    service = db.query(
        models.GarageService
    ).filter(
        models.GarageService.id == service_id,
        models.GarageService.garage_id == current_garage.id
    ).first()

    if not service:
        raise HTTPException(
            status_code=404,
            detail="Service not found"
        )

    # Toggle
    service.is_available = not service.is_available

    db.commit()
    db.refresh(service)

    return {
        "message": "Service status updated",
        "is_available": service.is_available
    }


# ──────────────────────────────────────────
# GET SERVICE BY SLUG
# GET /api/garage/me/services/slug/{slug}
# ──────────────────────────────────────────

@router.get("/me/services/slug/{slug}", response_model=schemas.GarageServiceResponse)
def get_service_by_slug(
    slug: str,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """Service ko slug se fetch karo."""
    service = db.query(models.GarageService).filter(
        models.GarageService.slug == slug,
        models.GarageService.garage_id == current_garage.id
    ).first()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    return service


# NearBy Garages 
def haversine_distance(lat1:float, lng1:float, lat2 :float,lng2:float) -> float:
    R = 6371
    d_lat = math.radians(lat2-lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2 
        + math.cos(math.radians(lat1))
        *math.cos(math.radians(lat2))
        *math.sin(d_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 -a))
    return R * c 

class NearbeGarageResponse(schemas.GaragePublicResponse):
    distance_km : float 
    is_open_noe : bool 

    class Config:
        from_attributes = True 


@router.get("/stats")
def get_public_stats(db: Session = Depends(get_db)):
    """Public stats for homepage — no auth needed."""
    total_garages = db.query(models.Garage).filter(models.Garage.is_active == True).count()
    return {"total_garages": total_garages}


@router.get("/nearby")
def get_nearby_garages(lat: float,lng: float,radius: float = 2.0,service_name: Opt[str] = None,db: Session = Depends(get_db),):
    """
    Customer ke aas paas ke garages fetch karo.
    - Haversine formula se distance calculate hoti hai
    - radius default 2km
    - service_name se filter optional (partial match)
    - Response mein distance_km, is_open_now, is_sos_available bhi aata hai
    """
    # Sirf active + verified garages jo location set kar chuke hain (LEFT JOIN to handle missing locations)
    garages = (
        db.query(models.Garage)
        .outerjoin(models.GarageLocation)
        .filter(
            models.Garage.is_active   == True,
            models.Garage.is_verified == True,
            models.Garage.is_credit_locked == False,
            models.GarageLocation.latitude  != None,
            models.GarageLocation.longitude != None,
        )
        .all()
    )
 
    # IST time (UTC + 5:30)
    from datetime import timedelta
    IST = timedelta(hours=5, minutes=30)
    now = dt.utcnow() + IST
    today = now.strftime("%A").lower()  # e.g. "monday"
 
    results = []
 
    for garage in garages:
        # Location check
        if not garage.location or not garage.location.latitude or not garage.location.longitude:
            continue
            
        loc = garage.location
        distance = haversine_distance(lat, lng, loc.latitude, loc.longitude)
 
        # Radius ke bahar — skip
        if distance > radius:
            continue
 
        # Service name filter — agar diya gaya hai
        if service_name:
            service_match = any(
                service_name.lower() in s.service_name.lower()
                for s in garage.services
                if s.is_available
            )
            if not service_match:
                continue
 
        # is_open_now calculate karo
        is_open_now = False
        try:
            for wh in garage.working_hours:
                if wh.day_of_week == today and wh.is_open:
                    if wh.open_time and wh.close_time:
                        current_time = now.time()
                        if wh.open_time <= current_time <= wh.close_time:
                            is_open_now = True
                    break
        except Exception as e:
            print(f"Working hours error for garage {garage.id}: {e}")
            is_open_now = True  # Default to open if error
 
        results.append({
            "id":                   garage.id,
            "slug":                 garage.slug,
            "name":                 garage.name,
            "phone":                garage.phone,
            "garage_type":          garage.garage_type,
            "logo_url":             garage.logo_url,
            "is_verified":          garage.is_verified,
            "offers_pick_and_drop": garage.offers_pick_and_drop,
            "is_sos_available":     garage.is_sos_available,
            "visiting_charge":      float(garage.visiting_charge) if garage.visiting_charge else 0.0,
            "location": {
                "id":          loc.id,
                "shop_number": loc.shop_number,
                "street":      loc.street,
                "city":        loc.city,
                "pincode":     loc.pincode,
                "latitude":    loc.latitude,
                "longitude":   loc.longitude,
            },
            "services": [
                {
                    "id":           s.id,
                    "service_name": s.service_name,
                    "category":     s.category,
                    "price":        float(s.price) if s.price else None,
                    "is_available": s.is_available,
                }
                for s in garage.services
                if s.is_available
            ],
            "distance_km": round(distance, 2),
            "is_open_now": is_open_now,
        })
 
    # Distance ke hisaab se sort karo (nearest first)
    results.sort(key=lambda x: x["distance_km"])
 
    return results
 
 


@router.get("/{garage_slug_or_id}/public")
def get_garage_public_detail(
    garage_slug_or_id: str,
    db: Session = Depends(get_db),
):
    """
    Garage detail page ke liye — no auth required.
    Slug ya ID dono se garage fetch karo.
    Customer is page pe services select karta hai aur booking karta hai.
    """
    # Try as integer ID first, else slug
    try:
        garage_id = int(garage_slug_or_id)
        garage = db.query(models.Garage).filter(
            models.Garage.id          == garage_id,
            models.Garage.is_active   == True,
            models.Garage.is_verified == True,
        ).first()
    except ValueError:
        garage = db.query(models.Garage).filter(
            models.Garage.slug        == garage_slug_or_id,
            models.Garage.is_active   == True,
            models.Garage.is_verified == True,
        ).first()
 
    if not garage:
        raise HTTPException(status_code=404, detail="Garage not found")
 
    # is_open_now (IST = UTC + 5:30)
    from datetime import timedelta as _td
    now   = dt.utcnow() + _td(hours=5, minutes=30)
    today = now.strftime("%A").lower()
    is_open_now    = False
    todays_hours   = None
 
    for wh in garage.working_hours:
        if wh.day_of_week == today:
            todays_hours = wh
            if wh.is_open and wh.open_time and wh.close_time:
                if wh.open_time <= now.time() <= wh.close_time:
                    is_open_now = True
            break
 
    # Services category wise group karo
    services_grouped = {}
    for s in garage.services:
        if not s.is_available:
            continue
        cat = s.category or "Other"
        if cat not in services_grouped:
            services_grouped[cat] = []
        services_grouped[cat].append({
            "id":           s.id,
            "service_name": s.service_name,
            "price":        float(s.price) if s.price else None,
            "is_available": s.is_available,
        })
 
    # Working hours full list
    working_hours = [
        {
            "day":        wh.day_of_week,
            "is_open":    wh.is_open,
            "open_time":  str(wh.open_time)  if wh.open_time  else None,
            "close_time": str(wh.close_time) if wh.close_time else None,
        }
        for wh in garage.working_hours
    ]
 
    loc = garage.location
 
    return {
        "id":                   garage.id,
        "name":                 garage.name,
        "phone":                garage.phone,
        "garage_type":          garage.garage_type,
        "logo_url":             garage.logo_url,
        "is_verified":          garage.is_verified,
        "is_sos_available":     garage.is_sos_available,
        "offers_pick_and_drop": garage.offers_pick_and_drop,
        "visiting_charge":      float(garage.visiting_charge) if garage.visiting_charge else 0.0,
        "is_open_now":          is_open_now,
        "todays_hours": {
            "open_time":  str(todays_hours.open_time)  if todays_hours and todays_hours.open_time  else None,
            "close_time": str(todays_hours.close_time) if todays_hours and todays_hours.close_time else None,
            "is_open":    todays_hours.is_open if todays_hours else False,
        } if todays_hours else None,
        "location": {
            "shop_number": loc.shop_number if loc else None,
            "street":      loc.street      if loc else None,
            "city":        loc.city        if loc else None,
            "pincode":     loc.pincode     if loc else None,
            "latitude":    loc.latitude    if loc else None,
            "longitude":   loc.longitude   if loc else None,
        },
        "services_grouped": services_grouped,
        "working_hours":    working_hours,
    }

# ──────────────────────────────────────────
# SUGGESTED SERVICES — GET
# GET /api/garage/me/suggested-services
# ──────────────────────────────────────────

@router.get("/me/suggested-services")
def get_suggested_services(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Mechanic ke garage_type ke according default services return karo
    jo usne abhi tak apni list mein add nahi ki hain.
    """
    garage_type = current_garage.garage_type  # two_wheeler | four_wheeler | both

    # Already added services ke naam (lowercase for comparison)
    existing_names = {
        s.service_name.lower()
        for s in current_garage.services
    }

    # Default services — garage type ke according filter
    query = db.query(models.DefaultService).filter(
        models.DefaultService.is_active == True
    )

    if garage_type == "two_wheeler":
        query = query.filter(
            models.DefaultService.vehicle_type.in_(["two_wheeler", "both"])
        )
    elif garage_type == "four_wheeler":
        query = query.filter(
            models.DefaultService.vehicle_type.in_(["four_wheeler", "both"])
        )
    # "both" ke liye sab dikhao — no extra filter

    all_defaults = query.order_by(
        models.DefaultService.category,
        models.DefaultService.id
    ).all()

    # Jo already add ho chuki hain unhe hataao
    suggestions = [
        {
            "id":              s.id,
            "vehicle_type":    s.vehicle_type,
            "category":        s.category,
            "service_name":    s.service_name,
            "suggested_price": float(s.suggested_price) if s.suggested_price else None,
            "price_type":      s.price_type,
        }
        for s in all_defaults
        if s.service_name.lower() not in existing_names
    ]

    return suggestions


# ──────────────────────────────────────────
# SUGGESTED SERVICES — ADD ONE
# POST /api/garage/me/suggested-services/{default_id}
# ──────────────────────────────────────────

@router.post("/me/suggested-services/{default_id}", status_code=201)
def add_suggested_service(
    default_id: int,
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Mechanic ek suggested service apni list mein add karta hai.
    Default service ka price aur category copy hoti hai.
    """
    default_svc = db.query(models.DefaultService).filter(
        models.DefaultService.id        == default_id,
        models.DefaultService.is_active == True
    ).first()

    if not default_svc:
        raise HTTPException(status_code=404, detail="Default service not found")

    # Already exist karta hai check
    existing = db.query(models.GarageService).filter(
        models.GarageService.garage_id    == current_garage.id,
        models.GarageService.service_name == default_svc.service_name
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Service already added")

    new_service = models.GarageService(
        garage_id    = current_garage.id,
        service_name = default_svc.service_name,
        category     = default_svc.category,
        price        = default_svc.suggested_price,
        is_available = True,
    )
    db.add(new_service)
    db.commit()
    db.refresh(new_service)

    return {
        "id":           new_service.id,
        "service_name": new_service.service_name,
        "category":     new_service.category,
        "price":        float(new_service.price) if new_service.price else None,
        "is_available": new_service.is_available,
    }