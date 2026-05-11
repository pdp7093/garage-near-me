from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, time
from enum import Enum


# ──────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────

class BookingType(str, Enum):
    normal = "normal"
    sos    = "sos"

class BookingStatus(str, Enum):
    pending   = "pending"
    accepted  = "accepted"
    rejected  = "rejected"
    ongoing   = "ongoing"
    completed = "completed"
    cancelled = "cancelled"

class EstimateStatus(str, Enum):
    not_required = "not_required"
    pending      = "pending"
    approved     = "approved"
    rejected     = "rejected"

class GarageRequestStatus(str, Enum):
    pending                = "pending"
    under_review           = "under_review"
    site_visit_scheduled   = "site_visit_scheduled"
    documents_pending      = "documents_pending"
    verification_completed = "verification_completed"
    approved               = "approved"
    rejected               = "rejected"


# ──────────────────────────────────────────
# CUSTOMER
# ──────────────────────────────────────────

class CustomerCreate(BaseModel):
    name:     str
    phone:    str
    email:    EmailStr
    password: str

class CustomerUpdate(BaseModel):
    name:  Optional[str] = None
    email: Optional[EmailStr] = None

class CustomerResponse(BaseModel):
    id:         int
    name:       str
    phone:      str
    email:      EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# AUTH (Customer)
# ──────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type:   str

class LoginRequest(BaseModel):
    phone:    str
    password: str


# ──────────────────────────────────────────
# GARAGE REQUEST (Onboarding Form)
# ──────────────────────────────────────────

class GarageRequestCreate(BaseModel):
    """Garage owner form bharta hai — public endpoint, no auth"""
    owner_name:  str
    garage_name: str
    phone:       str
    email:       Optional[EmailStr] = None
    garage_type: Optional[str] = None   # four_wheeler | two_wheeler | both
    address:     Optional[str] = None
    city:        str = "Ahmedabad"
    pincode:     Optional[str] = None

class GarageRequestResponse(BaseModel):
    id:                    int
    owner_name:            str
    garage_name:           str
    phone:                 str
    email:                 Optional[EmailStr] = None
    garage_type:           Optional[str] = None
    address:               Optional[str] = None
    city:                  str
    pincode:               Optional[str] = None
    status:                GarageRequestStatus
    admin_note:            Optional[str] = None
    visit_date:            Optional[datetime] = None
    visit_notes:           Optional[str] = None
    is_site_verified:      Optional[bool] = None
    is_documents_verified: Optional[bool] = None
    verification_notes:    Optional[str] = None
    created_at:            datetime
    documents:             List['GarageDocumentResponse'] = []

    class Config:
        from_attributes = True

class GarageRequestAdminUpdate(BaseModel):
    admin_note: Optional[str] = None


# ──────────────────────────────────────────
# GARAGE OTP AUTH
# ──────────────────────────────────────────

class OTPSendRequest(BaseModel):
    """Garage owner phone number dalta hai → OTP bhejo"""
    phone: str

class OTPVerifyRequest(BaseModel):
    """Garage owner OTP dalta hai → JWT token milta hai"""
    phone: str
    otp:   str

class OTPSendResponse(BaseModel):
    message: str
    # Testing ke liye OTP bhi return karenge (production mein hataana)
    otp:     Optional[str] = None


# ──────────────────────────────────────────
# GARAGE LOCATION
# ──────────────────────────────────────────

class GarageLocationCreate(BaseModel):
    shop_number: Optional[str] = None
    street:      Optional[str] = None
    city:        str = "Ahmedabad"
    pincode:     Optional[str] = None

class GarageLocationResponse(BaseModel):
    id:          int
    shop_number: Optional[str] = None
    street:      Optional[str] = None
    city:        str
    pincode:     Optional[str] = None
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# GARAGE WORKING HOURS
# ──────────────────────────────────────────

class WorkingHourItem(BaseModel):
    day_of_week: str
    is_open:     bool = True
    open_time:   Optional[time] = None
    close_time:  Optional[time] = None

class WorkingHourResponse(WorkingHourItem):
    id: int

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# GARAGE BANKING
# ──────────────────────────────────────────

class GarageBankingCreate(BaseModel):
    upi_id:         Optional[str] = None
    account_holder: Optional[str] = None
    bank_name:      Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code:      Optional[str] = None

class GarageBankingResponse(GarageBankingCreate):
    id: int

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# GARAGE SERVICES
# ──────────────────────────────────────────

class GarageServiceCreate(BaseModel):
    service_name: str
    price:        Optional[float] = None
    is_available: bool = True

class GarageServiceResponse(GarageServiceCreate):
    id: int

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# GARAGE DOCUMENTS
# ──────────────────────────────────────────

class GarageDocumentResponse(BaseModel):
    id:            int
    garage_id:     Optional[int] = None
    request_id:    Optional[int] = None
    document_type: str
    file_url:      str
    uploaded_at:   datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# GARAGE MAIN
# ──────────────────────────────────────────

class GarageUpdate(BaseModel):
    is_active:            Optional[bool]  = None
    name:                 Optional[str]   = None
    owner_name:           Optional[str]   = None
    garage_type:          Optional[str]   = None
    logo_url:             Optional[str]   = None
    is_sos_available:     Optional[bool]  = None
    offers_pick_and_drop: Optional[bool]  = None
    visiting_charge:      Optional[float] = None

class GarageResponse(BaseModel):
    id:                   int
    name:                 str
    owner_name:           str
    phone:                str
    email:                Optional[EmailStr] = None
    garage_type:          Optional[str]  = None
    logo_url:             Optional[str]  = None
    is_active:            bool
    is_verified:          bool
    is_sos_available:     bool
    offers_pick_and_drop: bool
    visiting_charge:      Optional[float] = None
    created_at:           datetime
    location:             Optional[GarageLocationResponse] = None
    working_hours:        List[WorkingHourResponse] = []
    banking:              Optional[GarageBankingResponse] = None
    services:             List[GarageServiceResponse] = []
    documents:            List[GarageDocumentResponse] = []

    class Config:
        from_attributes = True

class GaragePublicResponse(BaseModel):
    id:                   int
    name:                 str
    phone:                str
    garage_type:          Optional[str] = None
    logo_url:             Optional[str] = None
    is_verified:          bool
    offers_pick_and_drop: bool
    visiting_charge:      Optional[float] = None
    location:             Optional[GarageLocationResponse] = None
    services:             List[GarageServiceResponse] = []

    class Config:
        from_attributes = True

class GarageRequestReviewUpdate(BaseModel):
    visit_date: datetime | None = None
    visit_notes: str | None = None

    verification_notes: str | None = None

    is_site_verified: bool | None = None
    is_documents_verified: bool | None = None
    
# ──────────────────────────────────────────
# BOOKING
# ──────────────────────────────────────────

class BookingCreate(BaseModel):
    garage_id:              int
    booking_type:           BookingType = BookingType.normal
    vehicle_type:           Optional[str] = None
    vehicle_model:          Optional[str] = None
    vehicle_number:         Optional[str] = None
    service_type:           Optional[str] = None
    description:            Optional[str] = None
    customer_lat:           Optional[float] = None
    customer_lng:           Optional[float] = None
    customer_address:       Optional[str] = None
    scheduled_at:           Optional[datetime] = None
    requires_pick_and_drop: bool = False
    pickup_address:         Optional[str] = None

class SOSBookingCreate(BookingCreate):
    booking_type:     BookingType = BookingType.sos
    garage_id:        Optional[int] = None
    vehicle_type:     Optional[str] = None
    vehicle_model:    Optional[str] = None
    vehicle_number:   Optional[str] = None
    description:      Optional[str] = None
    customer_lat:     float
    customer_lng:     float
    customer_address: Optional[str] = None

class BookingStatusUpdate(BaseModel):
    status:      BookingStatus
    garage_note: Optional[str] = None

class BookingEstimateUpdate(BaseModel):
    estimated_amount: float
    estimate_status:  EstimateStatus
    pickup_charge:    Optional[float] = None

class EstimateApproval(BaseModel):
    estimate_status: EstimateStatus

class BookingResponse(BaseModel):
    id:                     int
    customer_id:            int
    garage_id:              int
    booking_type:           BookingType
    status:                 BookingStatus
    vehicle_type:           Optional[str] = None
    vehicle_model:          Optional[str] = None
    vehicle_number:         Optional[str] = None
    service_type:           Optional[str] = None
    description:            Optional[str] = None
    customer_lat:           Optional[float] = None
    customer_lng:           Optional[float] = None
    customer_address:       Optional[str] = None
    scheduled_at:           Optional[datetime] = None
    requires_pick_and_drop: bool
    pickup_address:         Optional[str] = None
    pickup_charge:          Optional[float] = None
    estimated_amount:       Optional[float] = None
    estimate_status:        EstimateStatus
    responded_at:           Optional[datetime] = None
    started_at:             Optional[datetime] = None
    completed_at:           Optional[datetime] = None
    final_amount:           Optional[float] = None
    payment_status:         Optional[str] = None
    created_at:             datetime

    class Config:
        from_attributes = True