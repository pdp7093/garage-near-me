from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime
import os

import models, schemas
from database import get_db
from utils.file_upload import save_garage_document

router = APIRouter()

# ──────────────────────────────────────────
# ADMIN AUTH
# ──────────────────────────────────────────

ADMIN_SECRET = os.getenv("ADMIN_SECRET", "gnm_admin_secret_2026")


def check_admin(x_admin_key: str):
    if x_admin_key != ADMIN_SECRET:
        raise HTTPException(
            status_code=403,
            detail="Invalid admin key"
        )


# ──────────────────────────────────────────
# 1. GARAGE REQUEST SUBMIT (Public)
# POST /api/garage-requests/
# ──────────────────────────────────────────

@router.post("/", response_model=schemas.GarageRequestResponse, status_code=201)
def submit_garage_request(
    request_data: schemas.GarageRequestCreate,
    db: Session = Depends(get_db)
):

    existing = db.query(models.GarageRequest).filter(
        models.GarageRequest.phone == request_data.phone,
        models.GarageRequest.status == models.GarageRequestStatus.pending
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="A request with this phone number is already pending review."
        )

    garage_exists = db.query(models.Garage).filter(
        models.Garage.phone == request_data.phone
    ).first()

    if garage_exists:
        raise HTTPException(
            status_code=400,
            detail="A garage with this phone number is already registered."
        )

    new_request = models.GarageRequest(
        owner_name=request_data.owner_name,
        garage_name=request_data.garage_name,
        phone=request_data.phone,
        email=request_data.email,
        garage_type=request_data.garage_type,
        address=request_data.address,
        city=request_data.city,
        pincode=request_data.pincode,
    )

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    return new_request


# ──────────────────────────────────────────
# 1.5 GARAGE REQUEST DOCUMENT UPLOAD (Public)
# POST /api/garage-requests/{request_id}/documents
# ──────────────────────────────────────────

@router.post("/{request_id}/documents", response_model=schemas.GarageDocumentResponse)
def upload_request_document(
    request_id: int,
    document_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Garage Owner uploads KYC documents after submitting the initial request.
    """
    req = db.query(models.GarageRequest).filter(models.GarageRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    file_url = save_garage_document(
        file,
        document_type=document_type,
        garage_name=req.garage_name,
        owner_name=req.owner_name,
    )
        
    doc = models.GarageDocument(
        request_id=request_id,
        document_type=document_type,
        file_url=file_url
    )
    db.add(doc)
    
    # Optional: Auto-update status to documents_pending if it's currently pending
    if req.status == models.GarageRequestStatus.pending:
        req.status = models.GarageRequestStatus.documents_pending

    db.commit()
    db.refresh(doc)
    return doc


# ──────────────────────────────────────────
# 2. GET ALL REQUESTS (Admin)
# ──────────────────────────────────────────

@router.get("/admin/all", response_model=list[schemas.GarageRequestResponse])
def get_all_requests(
    status: str = "pending",
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    query = db.query(models.GarageRequest)

    if status:
        try:
            status_enum = models.GarageRequestStatus(status)
            query = query.filter(
                models.GarageRequest.status == status_enum
            )
        except ValueError:
            pass

    return query.order_by(
        models.GarageRequest.created_at.desc()
    ).all()


# ──────────────────────────────────────────
# 3. START REVIEW
# ──────────────────────────────────────────

@router.post("/admin/{request_id}/start-review")
def start_review(
    request_id: int,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Request not found"
        )

    if req.status not in (models.GarageRequestStatus.pending, models.GarageRequestStatus.documents_pending):
        raise HTTPException(
            status_code=400,
            detail="Only pending or documents_pending requests can start review"
        )

    req.status = models.GarageRequestStatus.under_review

    db.commit()

    return {
        "message": "Review started successfully"
    }


# ──────────────────────────────────────────
# 4. SCHEDULE VISIT
# ──────────────────────────────────────────

@router.post("/admin/{request_id}/schedule-visit")
def schedule_visit(
    request_id: int,
    data: schemas.GarageRequestReviewUpdate,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Request not found"
        )

    if req.status != models.GarageRequestStatus.under_review:
        raise HTTPException(
            status_code=400,
            detail="Request must be under review first"
        )

    req.visit_date = data.visit_date
    req.visit_notes = data.visit_notes

    req.status = models.GarageRequestStatus.site_visit_scheduled

    db.commit()

    return {
        "message": "Site visit scheduled"
    }


# ──────────────────────────────────────────
# 5. COMPLETE VERIFICATION
# ──────────────────────────────────────────

@router.post("/admin/{request_id}/complete-verification")
def complete_verification(
    request_id: int,
    data: schemas.GarageRequestReviewUpdate,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Request not found"
        )

    if req.status != models.GarageRequestStatus.site_visit_scheduled:
        raise HTTPException(
            status_code=400,
            detail="Site visit must be scheduled first"
        )

    req.is_site_verified = data.is_site_verified
    req.is_documents_verified = data.is_documents_verified
    req.verification_notes = data.verification_notes

    req.status = models.GarageRequestStatus.verification_completed

    db.commit()

    return {
        "message": "Verification completed successfully"
    }


# ──────────────────────────────────────────
# 6. APPROVE REQUEST
# ──────────────────────────────────────────

@router.post(
    "/admin/{request_id}/approve",
    response_model=schemas.GarageResponse
)
def approve_garage_request(
    request_id: int,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Request not found"
        )

    if req.status != models.GarageRequestStatus.verification_completed:
        raise HTTPException(
            status_code=400,
            detail="Garage verification is not completed yet"
        )

    new_garage = models.Garage(
        name=req.garage_name,
        owner_name=req.owner_name,
        phone=req.phone,
        email=req.email,
        hashed_password=None,
        garage_type=req.garage_type,
        is_verified=True,
        is_active=True,
    )

    db.add(new_garage)
    db.flush()

    days = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday"
    ]

    for day in days:
        wh = models.GarageWorkingHours(
            garage_id=new_garage.id,
            day_of_week=day,
            is_open=day != "sunday",
            open_time=datetime.strptime("09:00", "%H:%M").time(),
            close_time=datetime.strptime("20:00", "%H:%M").time(),
        )
        db.add(wh)

    location = models.GarageLocation(
        garage_id=new_garage.id,
        street=req.address,
        city=req.city,
        pincode=req.pincode,
    )

    db.add(location)

    # Transfer request documents to the new garage
    for doc in req.documents:
        doc.garage_id = new_garage.id

    req.status = models.GarageRequestStatus.approved

    db.commit()
    db.refresh(new_garage)

    return new_garage


# ──────────────────────────────────────────
# 7. REJECT REQUEST
# ──────────────────────────────────────────

@router.post(
    "/admin/{request_id}/reject",
    response_model=schemas.GarageRequestResponse
)
def reject_garage_request(
    request_id: int,
    update: schemas.GarageRequestAdminUpdate,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Request not found"
        )

    if req.status == models.GarageRequestStatus.approved:
        raise HTTPException(
            status_code=400,
            detail="Approved request cannot be rejected"
        )

    req.status = models.GarageRequestStatus.rejected
    req.admin_note = update.admin_note

    db.commit()
    db.refresh(req)

    return req


# ──────────────────────────────────────────
# 10. UPLOAD GARAGE DOCUMENT (Admin)
# POST /api/garage-requests/admin/{garage_id}/documents
# ──────────────────────────────────────────

@router.post("/admin/{garage_id}/documents", response_model=schemas.GarageDocumentResponse)
def upload_garage_document(
    garage_id: int,
    document_type: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):
    """
    Admin uploads a verification document for a specific garage.
    """
    check_admin(x_admin_key)
    
    garage = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if not garage:
        raise HTTPException(status_code=404, detail="Garage not found")

    file_url = save_garage_document(
        file,
        document_type=document_type,
        garage_name=garage.name,
        owner_name=garage.owner_name,
    )
        
    doc = models.GarageDocument(
        garage_id=garage_id,
        document_type=document_type,
        file_url=file_url
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ──────────────────────────────────────────
# 8. REQUEST DETAILS
# ──────────────────────────────────────────

@router.get(
    "/admin/{request_id}",
    response_model=schemas.GarageRequestResponse
)
def get_request_details(
    request_id: int,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    req = db.query(models.GarageRequest).filter(
        models.GarageRequest.id == request_id
    ).first()

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Request not found"
        )

    return req


# ──────────────────────────────────────────
# 9. DASHBOARD STATS
# ──────────────────────────────────────────

@router.get("/admin/dashboard-stats")
def get_dashboard_stats(
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):

    check_admin(x_admin_key)

    total_requests = db.query(models.GarageRequest).count()

    pending_requests = db.query(models.GarageRequest).filter(
        models.GarageRequest.status ==
        models.GarageRequestStatus.pending
    ).count()

    under_review = db.query(models.GarageRequest).filter(
        models.GarageRequest.status ==
        models.GarageRequestStatus.under_review
    ).count()

    approved = db.query(models.GarageRequest).filter(
        models.GarageRequest.status ==
        models.GarageRequestStatus.approved
    ).count()

    rejected = db.query(models.GarageRequest).filter(
        models.GarageRequest.status ==
        models.GarageRequestStatus.rejected
    ).count()

    total_garages = db.query(models.Garage).count()

    return {
        "total_requests": total_requests,
        "pending_requests": pending_requests,
        "under_review": under_review,
        "approved": approved,
        "rejected": rejected,
        "total_garages": total_garages
    }
