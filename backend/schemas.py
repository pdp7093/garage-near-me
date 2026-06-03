from pydantic import BaseModel, EmailStr, field_validator
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

class SOSStatus(str, Enum):
    broadcasting = "broadcasting"
    accepted     = "accepted"
    on_the_way   = "on_the_way"
    in_progress  = "in_progress"
    completed    = "completed"
    cancelled    = "cancelled"

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
    profile_image: Optional[str] = None

class CustomerResponse(BaseModel):
    id:         int
    name:       str
    phone:      str
    email:      EmailStr
    profile_image: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# CUSTOMER ADDRESS
# ──────────────────────────────────────────

class CustomerAddressCreate(BaseModel):
    title:      Optional[str] = None
    address:    str
    latitude:   Optional[float] = None
    longitude:  Optional[float] = None
    is_default: bool = False

class CustomerAddressResponse(BaseModel):
    id:         int
    customer_id:int
    title:      Optional[str] = None
    address:    str
    latitude:   Optional[float] = None
    longitude:  Optional[float] = None
    is_default: bool
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
    has_gst:     bool = False
    gst_number:  Optional[str] = None

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
    has_gst:               bool
    gst_number:            Optional[str] = None
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

class FCMTokenUpdate(BaseModel):
    fcm_token: str


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
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None

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
    category:     Optional[str] = None
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
    has_gst:              Optional[bool]  = None
    gst_number:           Optional[str]   = None

class GarageResponse(BaseModel):
    id:                   int
    slug:                 Optional[str]  = None
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
    has_gst:              bool
    gst_number:           Optional[str] = None
    pending_platform_dues: float
    is_credit_locked:     bool
    grace_period_ends_at:  Optional[datetime] = None
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
    slug:                 Optional[str] = None
    name:                 str
    phone:                str
    garage_type:          Optional[str] = None
    logo_url:             Optional[str] = None
    is_verified:          bool
    offers_pick_and_drop: bool
    visiting_charge:      Optional[float] = None
    has_gst:              bool
    gst_number:           Optional[str] = None
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
    final_amount: Optional[float] = None

class PaymentStatusUpdate(BaseModel):
    payment_status: str

class EstimateItem(BaseModel):
    item_name: str
    price: float

class BookingEstimateUpdate(BaseModel):
    estimate_details: list[EstimateItem]
    estimate_status:  EstimateStatus
    pickup_charge:    Optional[float] = None
    has_hidden_issues: bool = False

class EstimateApproval(BaseModel):
    estimate_status: EstimateStatus

class BookingResponse(BaseModel):
    id:                     int
    slug:                   Optional[str] = None
    booking_number:         Optional[str] = None
    customer_id:            int
    customer_name:          Optional[str] = None
    customer_phone:         Optional[str] = None
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
    estimate_details:       Optional[list[dict]] = None
    estimate_status:        Optional[EstimateStatus] = None
    has_hidden_issues:      bool = False
    additional_estimate:    Optional[float] = None
    additional_estimate_note: Optional[str] = None
    additional_estimate_details: Optional[list[dict]] = None
    additional_otp_verified: bool = False
    responded_at:           Optional[datetime] = None
    started_at:             Optional[datetime] = None
    completed_at:           Optional[datetime] = None
    final_amount:           Optional[float] = None
    platform_commission:    Optional[float] = None
    garage_earnings:        Optional[float] = None
    payment_status:         Optional[str] = None
    created_at:             datetime
    # Garage info — visiting_charge ke liye (booking router inject karta hai)
    garage_visiting_charge: Optional[float] = None
    garage_name:            Optional[str] = None
    garage_address:         Optional[str] = None

    model_config = {"from_attributes": True}

class PaginatedBookingResponse(BaseModel):
    items: List[BookingResponse]
    total: int
    page: int
    size: int
    pages: int


# ──────────────────────────────────────────
# SOS (EMERGENCY BREAKDOWN)
# ──────────────────────────────────────────

class SOSCreate(BaseModel):
    # Accept both old (lat/lng) and new (latitude/longitude) formats
    latitude:          Optional[float] = None
    longitude:         Optional[float] = None
    lat:               Optional[float] = None  # Old format from frontend
    lng:               Optional[float] = None  # Old format from frontend
    address:           Optional[str] = None
    vehicle_type:      str  # two_wheeler | four_wheeler
    vehicle_number:    Optional[str] = None
    vehicle_model:     Optional[str] = None
    description:       Optional[str] = None
    broadcast_radius_km: Optional[float] = 2.0
    radius_km:         Optional[float] = None  # Old format from frontend

class SOSUpdate(BaseModel):
    description:       Optional[str] = None
    address:           Optional[str] = None

class SOSResponse(BaseModel):
    id:                  int
    slug:                Optional[str] = None
    sos_number:          Optional[str] = None
    customer_id:         int
    garage_id:           Optional[int] = None
    latitude:            float
    longitude:           float
    address:             Optional[str] = None
    broadcast_radius_km: float
    vehicle_type:        str
    vehicle_number:      Optional[str] = None
    vehicle_model:       Optional[str] = None
    description:         Optional[str] = None
    status:              SOSStatus
    estimated_charge:    Optional[float] = None
    visiting_charge:     Optional[float] = None
    final_charge:        Optional[float] = None
    platform_commission: Optional[float] = None
    garage_earnings:     Optional[float] = None
    created_at:          datetime
    accepted_at:         Optional[datetime] = None
    started_at:          Optional[datetime] = None
    completed_at:        Optional[datetime] = None
    updated_at:          Optional[datetime] = None
    distance_km:         Optional[float] = None
    customer_address:    Optional[str] = None
    
    model_config = {"from_attributes": True}

class PaginatedSOSResponse(BaseModel):
    items: List[SOSResponse]
    total: int
    page: int
    size: int
    pages: int


# ──────────────────────────────────────────
# DEFAULT SERVICES
# ──────────────────────────────────────────

class DefaultServiceCreate(BaseModel):
    vehicle_type:    str            # two_wheeler | four_wheeler | both
    category:        str            # General Service | Repair Service | Major Repair
    service_name:    str
    suggested_price: Optional[float] = None
    price_type:      str = "fixed"  # fixed | starting | estimate | quote
    is_active:       bool = True

class DefaultServiceUpdate(BaseModel):
    vehicle_type:    Optional[str]   = None
    category:        Optional[str]   = None
    service_name:    Optional[str]   = None
    suggested_price: Optional[float] = None
    price_type:      Optional[str]   = None
    is_active:       Optional[bool]  = None

class DefaultServiceResponse(BaseModel):
    id:              int
    vehicle_type:    str
    category:        str
    service_name:    str
    suggested_price: Optional[float] = None
    price_type:      str
    is_active:       bool
    created_at:      datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# GARAGE SERVICE — Update schema (PATCH)
# ──────────────────────────────────────────

class GarageServiceUpdate(BaseModel):
    service_name: Optional[str]   = None
    category:     Optional[str]   = None
    price:        Optional[float] = None
    is_available: Optional[bool]  = None


# ──────────────────────────────────────────
# BILL / INVOICE
# ──────────────────────────────────────────

class BillCreate(BaseModel):
    booking_id:      int
    subtotal:        float
    tax_amount:      float = 0
    total_amount:    float
    items:           Optional[list] = None
    garage_name:     Optional[str]  = None
    garage_address:  Optional[str]  = None
    garage_gst:      Optional[str]  = None
    customer_name:   Optional[str]  = None
    vehicle_info:    Optional[str]  = None
    service_type:    Optional[str]  = None

class BillResponse(BaseModel):
    id:              int
    booking_id:      int
    customer_id:     int
    garage_id:       int
    bill_number:     Optional[str]
    bill_date:       datetime
    subtotal:        float
    tax_amount:      float
    total_amount:    float
    platform_commission: Optional[float] = None
    garage_earnings:     Optional[float] = None
    items:           Optional[list] = None
    garage_name:     Optional[str]
    garage_address:  Optional[str]
    garage_gst:      Optional[str]
    customer_name:   Optional[str]
    vehicle_info:    Optional[str]
    service_type:    Optional[str]
    created_at:      datetime

    class Config:
        from_attributes = True

# ──────────────────────────────────────────
# COMMISSION RULES
# ──────────────────────────────────────────

class CommissionRuleCreate(BaseModel):
    min_amount: float
    max_amount: Optional[float] = None
    percentage: float
    is_active:  bool = True

class CommissionRuleUpdate(BaseModel):
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    percentage: Optional[float] = None
    is_active:  Optional[bool] = None

class CommissionRuleResponse(BaseModel):
    id:         int
    min_amount: float
    max_amount: Optional[float] = None
    percentage: float
    is_active:  bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# PLATFORM PAYOUT REQUESTS
# ──────────────────────────────────────────

class PlatformPayoutRequestCreate(BaseModel):
    amount:     float
    utr_number: str

class PlatformPayoutRequestAction(BaseModel):
    action:     str  # "approve" | "reject"

class PlatformPayoutRequestResponse(BaseModel):
    id:             int
    garage_id:      int
    amount:         float
    utr_number:     str
    screenshot_url: Optional[str] = None
    status:         str
    created_at:     datetime
    updated_at:     Optional[datetime] = None
    garage_name:    Optional[str] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# PLATFORM ADMINS
# ──────────────────────────────────────────

class AdminCreate(BaseModel):
    email:    str
    password: str

class AdminLoginRequest(BaseModel):
    email:    str
    password: str

class AdminResponse(BaseModel):
    id:         int
    email:      str
    created_at: datetime

    class Config:
        from_attributes = True