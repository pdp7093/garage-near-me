from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import os
from fastapi import UploadFile, File, Form
import models, schemas
from database import get_db
from utils.file_upload import save_garage_document

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
        models.Garage.is_verified == True
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
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    """Admin — saare garages fetch karo (active + inactive dono)"""
    if x_admin_key != os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026"):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    
    return db.query(models.Garage).order_by(models.Garage.created_at.desc()).all()

# Admin : Get single garage by ID 
@router.get("/admin/{garage_id}", response_model=schemas.GarageResponse)
def get_garage_by_id_admin(garage_id:int, x_admin_key: str =Header(None), db:Session = Depends(get_db)):
    if x_admin_key != os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026"):
        raise HTTPException(status_code=403, detail="Invalid admin key")
    g = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garage not found")
    return g


# ── ADMIN: Toggle status
@router.patch("/admin/{garage_id}/toggle-status", response_model=schemas.GarageResponse)
def toggle_garage_status(
    garage_id: int,
    data: schemas.GarageUpdate,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    if x_admin_key != os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026"):
        raise HTTPException(status_code=403, detail="Invalid admin key")
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
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    if x_admin_key != os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026"):
        raise HTTPException(status_code=403, detail="Invalid admin key")
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
    # TEMP BUSINESS METRICS
    # (Until booking system is built)
    # ─────────────────────────────

    todays_earnings = services_count * 250

    jobs_completed = services_count

    active_sos = 1 if current_garage.is_sos_available else 0

    customer_rating = round(
        3.5 + (profile_completion / 100) * 1.5,
        1
    )


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
        "todays_earnings": todays_earnings,
        "jobs_completed": jobs_completed,
        "active_sos": active_sos,
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
