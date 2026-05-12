from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Optional
import os

import models, schemas
from database import get_db

router = APIRouter()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026")

def verify_admin(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin key")


# ──────────────────────────────────────────
# GET ALL DEFAULT SERVICES
# GET /api/default-services
# Optional filter: ?vehicle_type=two_wheeler
# ──────────────────────────────────────────

@router.get("/", response_model=List[schemas.DefaultServiceResponse])
def get_default_services(
    vehicle_type: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.DefaultService).filter(
        models.DefaultService.is_active == True
    )
    if vehicle_type:
        query = query.filter(
            (models.DefaultService.vehicle_type == vehicle_type) |
            (models.DefaultService.vehicle_type == "both")
        )
    if category:
        query = query.filter(models.DefaultService.category == category)

    return query.order_by(
        models.DefaultService.vehicle_type,
        models.DefaultService.category,
        models.DefaultService.id
    ).all()


# ──────────────────────────────────────────
# GET ALL DEFAULT SERVICES (ADMIN — including inactive)
# GET /api/default-services/admin/all
# ──────────────────────────────────────────

@router.get("/admin/all", response_model=List[schemas.DefaultServiceResponse])
def get_all_default_services_admin(
    vehicle_type: Optional[str] = None,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    query = db.query(models.DefaultService)
    if vehicle_type:
        query = query.filter(models.DefaultService.vehicle_type == vehicle_type)
    return query.order_by(
        models.DefaultService.vehicle_type,
        models.DefaultService.category,
        models.DefaultService.id
    ).all()


# ──────────────────────────────────────────
# CREATE DEFAULT SERVICE (ADMIN)
# POST /api/default-services/
# ──────────────────────────────────────────

@router.post("/", response_model=schemas.DefaultServiceResponse, status_code=201)
def create_default_service(
    data: schemas.DefaultServiceCreate,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    service = models.DefaultService(
        vehicle_type    = data.vehicle_type,
        category        = data.category,
        service_name    = data.service_name,
        suggested_price = data.suggested_price,
        price_type      = data.price_type,
        is_active       = data.is_active
    )
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


# ──────────────────────────────────────────
# UPDATE DEFAULT SERVICE (ADMIN)
# PATCH /api/default-services/{id}
# ──────────────────────────────────────────

@router.patch("/{service_id}", response_model=schemas.DefaultServiceResponse)
def update_default_service(
    service_id: int,
    data: schemas.DefaultServiceUpdate,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    service = db.query(models.DefaultService).filter(
        models.DefaultService.id == service_id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Default service not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)

    db.commit()
    db.refresh(service)
    return service


# ──────────────────────────────────────────
# DELETE DEFAULT SERVICE (ADMIN)
# DELETE /api/default-services/{id}
# ──────────────────────────────────────────

@router.delete("/{service_id}", status_code=204)
def delete_default_service(
    service_id: int,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    service = db.query(models.DefaultService).filter(
        models.DefaultService.id == service_id
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Default service not found")

    db.delete(service)
    db.commit()
    return None


# ──────────────────────────────────────────
# BULK CREATE DEFAULT SERVICES (ADMIN)
# POST /api/default-services/bulk
# Ek saath saari services add karo
# ──────────────────────────────────────────

@router.post("/bulk", response_model=List[schemas.DefaultServiceResponse], status_code=201)
def bulk_create_default_services(
    data: List[schemas.DefaultServiceCreate],
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    services = []
    for item in data:
        service = models.DefaultService(
            vehicle_type    = item.vehicle_type,
            category        = item.category,
            service_name    = item.service_name,
            suggested_price = item.suggested_price,
            price_type      = item.price_type,
            is_active       = item.is_active
        )
        db.add(service)
        services.append(service)
    db.commit()
    for s in services:
        db.refresh(s)
    return services