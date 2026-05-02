from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime, time


# ──────────────────────────────────────────
# CUSTOMER
# ──────────────────────────────────────────

class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: EmailStr
    password: str

class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    phone: str
    password: str


# ──────────────────────────────────────────
# GARAGE LOCATION
# ──────────────────────────────────────────

class GarageLocationCreate(BaseModel):
    shop_number: Optional[str] = None
    street:      Optional[str] = None
    city:        str = "Ahmedabad"
    pincode:     Optional[str] = None
    # latitude / longitude GPS baad mein

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
    day_of_week: str          # "monday" ... "sunday"
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
    service_name:  str
    price:         Optional[float] = None
    is_available:  bool = True

class GarageServiceResponse(GarageServiceCreate):
    id: int

    class Config:
        from_attributes = True


# ──────────────────────────────────────────
# GARAGE MAIN
# ──────────────────────────────────────────

class GarageCreate(BaseModel):
    name:        str
    owner_name:  str
    phone:       str
    email:       Optional[EmailStr] = None
    password:    str
    garage_type: Optional[str] = None   # four_wheeler | two_wheeler | both

class GarageUpdate(BaseModel):
    name:             Optional[str] = None
    owner_name:       Optional[str] = None
    garage_type:      Optional[str] = None
    logo_url:         Optional[str] = None
    is_sos_available: Optional[bool] = None

class GarageResponse(BaseModel):
    id:               int
    name:             str
    owner_name:       str
    phone:            str
    email:            Optional[EmailStr] = None
    garage_type:      Optional[str] = None
    logo_url:         Optional[str] = None
    is_active:        bool
    is_verified:      bool
    is_sos_available: bool
    created_at:       datetime

    # Nested
    location:      Optional[GarageLocationResponse] = None
    working_hours: List[WorkingHourResponse] = []
    banking:       Optional[GarageBankingResponse] = None
    services:      List[GarageServiceResponse] = []

    class Config:
        from_attributes = True


class GaragePublicResponse(BaseModel):
    """Customer ko dikhne wala — verified garages only, no sensitive info"""
    id:          int
    name:        str
    phone:       str
    garage_type: Optional[str] = None
    logo_url:    Optional[str] = None
    is_verified: bool
    location:    Optional[GarageLocationResponse] = None
    services:    List[GarageServiceResponse] = []

    class Config:
        from_attributes = True