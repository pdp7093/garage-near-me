from fastapi import APIRouter, Depends, HTTPException, status, Header, Form, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
import os
from datetime import datetime, timedelta, timezone
import models, schemas
from database import get_db
from routers.garage import get_current_garage
from utils.file_upload import save_payout_screenshot

router = APIRouter()

def verify_admin(x_admin_key: str = Header(None)):
    ADMIN_SECRET = os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026")
    if x_admin_key == ADMIN_SECRET:
        return
    
    if not x_admin_key:
        raise HTTPException(status_code=401, detail="Admin token required")
    
    from jose import jwt, JWTError
    from routers.auth import SECRET_KEY, ALGORITHM
    
    try:
        payload = jwt.decode(x_admin_key, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        if not email or role != "admin":
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

# ──────────────────────────────────────────
# 1. GARAGE: SUBMIT PAYOUT PROOF
# POST /api/payouts/request
# ──────────────────────────────────────────

@router.post("/request", response_model=schemas.PlatformPayoutRequestResponse)
def submit_payout_request(
    amount: float = Form(...),
    utr_number: str = Form(...),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage uploads a manual bank payment proof (UTR and screenshot) to reset/deduct dues.
    """
    screenshot_url = None
    if file:
        try:
            screenshot_url = save_payout_screenshot(file, current_garage.id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save screenshot: {str(e)}")

    # Check for duplicate UTR in pending/approved requests to prevent double submissions
    duplicate = db.query(models.PlatformPayoutRequest).filter(
        models.PlatformPayoutRequest.utr_number == utr_number,
        models.PlatformPayoutRequest.status.in_(["pending", "approved"])
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=400,
            detail="A payout request with this UTR number already exists and is pending or approved."
        )

    payout_req = models.PlatformPayoutRequest(
        garage_id=current_garage.id,
        amount=amount,
        utr_number=utr_number,
        screenshot_url=screenshot_url,
        status="pending"
    )

    db.add(payout_req)
    db.commit()
    db.refresh(payout_req)

    # Inject garage_name to response
    payout_req_dict = schemas.PlatformPayoutRequestResponse.model_validate(payout_req)
    payout_req_dict.garage_name = current_garage.name

    return payout_req_dict


# ──────────────────────────────────────────
# 2. GARAGE: VIEW PAYOUT HISTORY / LEDGER
# GET /api/payouts/garage/my-requests
# ──────────────────────────────────────────

@router.get("/garage/my-requests", response_model=List[schemas.PlatformPayoutRequestResponse])
def get_my_payout_requests(
    db: Session = Depends(get_db),
    current_garage: models.Garage = Depends(get_current_garage)
):
    """
    Garage fetches their past payout proof submissions (ledger).
    """
    requests = db.query(models.PlatformPayoutRequest).filter(
        models.PlatformPayoutRequest.garage_id == current_garage.id
    ).order_by(models.PlatformPayoutRequest.created_at.desc()).all()

    response = []
    for r in requests:
        res_item = schemas.PlatformPayoutRequestResponse.model_validate(r)
        res_item.garage_name = current_garage.name
        response.append(res_item)

    return response


# ──────────────────────────────────────────
# 3. ADMIN: VIEW ALL PENDING/PAST REQUESTS
# GET /api/payouts/admin/all-requests
# ──────────────────────────────────────────

@router.get("/admin/all-requests", response_model=List[schemas.PlatformPayoutRequestResponse])
def get_all_payout_requests_admin(
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin fetches all payout request submissions from all garages.
    """
    verify_admin(x_admin_key)

    requests = db.query(models.PlatformPayoutRequest).order_by(
        models.PlatformPayoutRequest.created_at.desc()
    ).all()

    response = []
    for r in requests:
        res_item = schemas.PlatformPayoutRequestResponse.model_validate(r)
        res_item.garage_name = r.garage.name if r.garage else "Unknown Garage"
        response.append(res_item)

    return response


# ──────────────────────────────────────────
# 4. ADMIN: APPROVE/REJECT REQUEST
# POST /api/payouts/admin/action/{payout_id}
# ──────────────────────────────────────────

@router.post("/admin/action/{payout_id}")
def process_payout_request_admin(
    payout_id: int,
    action_data: schemas.PlatformPayoutRequestAction,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin approves or rejects a payout verification request.
    If approved, deducts dues from the garage and unlocks credit if dues fall below ₹500.
    """
    verify_admin(x_admin_key)

    payout_req = db.query(models.PlatformPayoutRequest).filter(
        models.PlatformPayoutRequest.id == payout_id
    ).first()

    if not payout_req:
        raise HTTPException(status_code=404, detail="Payout request not found")

    if payout_req.status != "pending":
        raise HTTPException(status_code=400, detail="This request has already been processed.")

    if action_data.action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'.")

    payout_req.status = "approved" if action_data.action == "approve" else "rejected"

    if action_data.action == "approve":
        garage = db.query(models.Garage).filter(models.Garage.id == payout_req.garage_id).first()
        if garage:
            if garage.pending_platform_dues is None:
                garage.pending_platform_dues = 0.0
            
            # Deduct dues (floor to 0)
            garage.pending_platform_dues = max(0.0, float(garage.pending_platform_dues) - float(payout_req.amount))
            
            # Unlock and reset grace period if dues fall below 500
            if garage.pending_platform_dues < 500.0:
                garage.is_credit_locked = False
                garage.grace_period_ends_at = None

    db.commit()

    return {"message": f"Payout request successfully {payout_req.status}."}


# ──────────────────────────────────────────
# 5. ADMIN: GENERATE WEEKLY STATEMENTS
# POST /api/payouts/admin/generate-weekly-statements
# ──────────────────────────────────────────

@router.post("/admin/generate-weekly-statements")
def generate_weekly_statements(
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    """
    Admin triggers weekly statement generation (usually run on Mondays).
    Finds all active, verified garages with outstanding dues >= 500.0
    and starts a strict 24-hour grace period for payment.
    """
    verify_admin(x_admin_key)

    # Find active, verified garages with dues >= 500.0 and no active grace period
    garages = db.query(models.Garage).filter(
        models.Garage.is_active == True,
        models.Garage.is_verified == True,
        models.Garage.pending_platform_dues >= 500.0,
        models.Garage.grace_period_ends_at == None
    ).all()

    now = datetime.utcnow()
    deadline = now + timedelta(hours=24)

    count = 0
    for g in garages:
        g.grace_period_ends_at = deadline
        count += 1

    db.commit()

    return {
        "message": f"Successfully generated weekly billing statements for {count} garages.",
        "count": count,
        "due_date": deadline.isoformat()
    }
