from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

import models, schemas
from database import get_db
from routers.vehicles import get_current_customer # Reusing auth dependency

router = APIRouter()

@router.get("/", response_model=List[schemas.CustomerAddressResponse])
def get_my_addresses(
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """Apni saari saved addresses dekho"""
    return db.query(models.CustomerAddress).filter(
        models.CustomerAddress.customer_id == current_customer.id
    ).order_by(models.CustomerAddress.created_at.desc()).all()


@router.post("/", response_model=schemas.CustomerAddressResponse, status_code=201)
def add_address(
    address_data: schemas.CustomerAddressCreate,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """Naya address add karo"""
    # If this is set to default, unset others for this customer
    if address_data.is_default:
        db.query(models.CustomerAddress).filter(
            models.CustomerAddress.customer_id == current_customer.id
        ).update({"is_default": False})

    new_address = models.CustomerAddress(
        customer_id=current_customer.id,
        title=address_data.title,
        address=address_data.address,
        latitude=address_data.latitude,
        longitude=address_data.longitude,
        is_default=address_data.is_default
    )
    db.add(new_address)
    db.commit()
    db.refresh(new_address)
    return new_address


@router.delete("/{address_id}", status_code=204)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    current_customer: models.Customer = Depends(get_current_customer)
):
    """Saved address delete karo"""
    address = db.query(models.CustomerAddress).filter(
        models.CustomerAddress.id == address_id,
        models.CustomerAddress.customer_id == current_customer.id
    ).first()
    
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")

    db.delete(address)
    db.commit()
    return None
