from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List
import os

import models, schemas
from database import get_db

router = APIRouter()

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026")

def verify_admin(x_admin_key: str = Header(None)):
    if x_admin_key != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin key")

@router.get("/", response_model=List[schemas.CommissionRuleResponse])
def get_commission_rules(
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    return db.query(models.CommissionRule).order_by(models.CommissionRule.min_amount).all()

@router.post("/", response_model=schemas.CommissionRuleResponse, status_code=201)
def create_commission_rule(
    data: schemas.CommissionRuleCreate,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    # Basic validation
    if data.max_amount is not None and data.min_amount >= data.max_amount:
        raise HTTPException(status_code=400, detail="max_amount must be greater than min_amount")

    rule = models.CommissionRule(
        min_amount=data.min_amount,
        max_amount=data.max_amount,
        percentage=data.percentage,
        is_active=data.is_active
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule

@router.delete("/{rule_id}", status_code=204)
def delete_commission_rule(
    rule_id: int,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_admin(x_admin_key)
    rule = db.query(models.CommissionRule).filter(models.CommissionRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Commission rule not found")
    
    db.delete(rule)
    db.commit()
    return None
