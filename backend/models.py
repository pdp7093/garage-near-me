from sqlalchemy import (
    Column, Integer, String, DateTime, Float,
    Boolean, ForeignKey, Text, Time, Numeric, Enum
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import enum


# ──────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────

class BookingType(str, enum.Enum):
    normal = "normal"
    sos    = "sos"

class BookingStatus(str, enum.Enum):
    pending   = "pending"
    accepted  = "accepted"
    rejected  = "rejected"
    ongoing   = "ongoing"
    completed = "completed"
    cancelled = "cancelled"

class SOSStatus(str, enum.Enum):
    broadcasting  = "broadcasting"   # Broadcast ho raha hai 2km radius ke garages ko
    accepted      = "accepted"       # Garage ne accept kiya
    on_the_way    = "on_the_way"    # Mechanic on the way
    in_progress   = "in_progress"   # Work in progress
    completed     = "completed"     # Complete ho gaya
    cancelled     = "cancelled"     # Customer ne cancel kiya ya garage rejected

class EstimateStatus(str, enum.Enum):
    not_required = "not_required"
    pending      = "pending"
    approved     = "approved"
    rejected     = "rejected"

class GarageRequestStatus(str, enum.Enum):
    pending = "pending"
    under_review = "under_review"
    site_visit_scheduled = "site_visit_scheduled"
    documents_pending = "documents_pending"
    verification_completed = "verification_completed"
    approved = "approved"
    rejected = "rejected"


# ──────────────────────────────────────────
# CUSTOMER
# ──────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(255), nullable=False, index=True)
    phone           = Column(String(15), unique=True, nullable=False, index=True)
    email           = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(Text, nullable=False)
    profile_image   = Column(String(500), nullable=True)  # URL to profile image
    fcm_token       = Column(Text, nullable=True)           # Firebase push notification token
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    bookings        = relationship("Booking", back_populates="customer", cascade="all, delete-orphan")
    vehicles        = relationship("Vehicle", back_populates="customer", cascade="all, delete-orphan")
    addresses       = relationship("CustomerAddress", back_populates="customer", cascade="all, delete-orphan")

# ──────────────────────────────────────────
# CUSTOMER ADDRESS
# ──────────────────────────────────────────

class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id          = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    title       = Column(String(50), nullable=True) # e.g. "Home", "Office"
    address     = Column(Text, nullable=False)
    latitude    = Column(Float, nullable=True)
    longitude   = Column(Float, nullable=True)
    is_default  = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    customer    = relationship("Customer", back_populates="addresses")



# ──────────────────────────────────────────
# VEHICLE
# ──────────────────────────────────────────

class Vehicle(Base):
    __tablename__ = "vehicles"

    id             = Column(Integer, primary_key=True, index=True)
    customer_id    = Column(Integer, ForeignKey("customers.id"), nullable=False)
    vehicle_type   = Column(String(20), nullable=True)
    vehicle_number = Column(String(20), nullable=True)
    description    = Column(String(255), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    customer       = relationship("Customer", back_populates="vehicles")


# ──────────────────────────────────────────
# GARAGE REQUEST (Onboarding)
# Garage owner request bhejta hai → admin approve karta hai → garages table mein jaata hai
# ──────────────────────────────────────────

class GarageRequest(Base):
    __tablename__ = "garage_requests"

    id           = Column(Integer, primary_key=True, index=True)

    # Basic Info
    owner_name   = Column(String(255), nullable=False)
    garage_name  = Column(String(255), nullable=False)
    phone        = Column(String(15), nullable=False, index=True)
    email        = Column(String(255), nullable=True)

    # Garage Type
    garage_type  = Column(String(50), nullable=True)   # four_wheeler | two_wheeler | both

    # Location
    address      = Column(Text, nullable=True)
    city         = Column(String(100), nullable=False, default="Ahmedabad")
    pincode      = Column(String(10), nullable=True)

    # GST
    has_gst      = Column(Boolean, default=False)
    gst_number   = Column(String(50), nullable=True)

    visit_date = Column(DateTime, nullable=True)
    visit_notes = Column(Text, nullable=True)

    verification_notes = Column(Text, nullable=True)

    rejection_reason = Column(Text, nullable=True)

    is_site_verified = Column(Boolean, default=False)
    is_documents_verified = Column(Boolean, default=False)
    # Status
    status       = Column(Enum(GarageRequestStatus), default=GarageRequestStatus.pending)

    # Admin note (rejection reason etc.)
    admin_note   = Column(Text, nullable=True)

    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())

    documents    = relationship("GarageDocument", back_populates="request", cascade="all, delete-orphan")


# ──────────────────────────────────────────
# GARAGE OTP (Login ke liye)
# Phone pe OTP bhejo → verify karo → JWT token milta hai
# ──────────────────────────────────────────

class GarageOTP(Base):
    __tablename__ = "garage_otps"

    id         = Column(Integer, primary_key=True, index=True)
    phone      = Column(String(15), nullable=False, index=True)
    otp        = Column(String(6), nullable=False)
    is_used    = Column(Boolean, default=False)     # ek baar use hone ke baad True
    expires_at = Column(DateTime(timezone=True), nullable=False)  # 10 min expiry
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ──────────────────────────────────────────
# GARAGE (Main Table)
# Sirf admin approve karne ke baad yahan entry aati hai
# ──────────────────────────────────────────

class Garage(Base):
    __tablename__ = "garages"

    id                   = Column(Integer, primary_key=True, index=True)
    slug                 = Column(String(300), unique=True, nullable=True, index=True)
    name                 = Column(String(255), nullable=False, index=True)
    owner_name           = Column(String(255), nullable=False)
    phone                = Column(String(15), unique=True, nullable=False, index=True)
    email                = Column(String(255), unique=True, nullable=True)
    hashed_password      = Column(Text, nullable=True)   # OTP login mein password nahi

    garage_type          = Column(String(50), nullable=True)
    logo_url             = Column(Text, nullable=True)

    is_active            = Column(Boolean, default=True)
    is_verified          = Column(Boolean, default=True)   # admin ne approve kiya toh verified
    is_sos_available     = Column(Boolean, default=True)
    offers_pick_and_drop = Column(Boolean, default=False)
    visiting_charge      = Column(Numeric(10, 2), default=0.0)

    # GST
    has_gst              = Column(Boolean, default=False)
    gst_number           = Column(String(50), nullable=True)

    fcm_token             = Column(Text, nullable=True)    # Firebase push notification token

    # Credit lock & platform dues system
    pending_platform_dues = Column(Numeric(10, 2), default=0.0)
    is_credit_locked      = Column(Boolean, default=False)
    grace_period_ends_at  = Column(DateTime(timezone=True), nullable=True)
    has_completed_trial   = Column(Boolean, default=False)

    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), onupdate=func.now())

    location      = relationship("GarageLocation",     back_populates="garage", uselist=False, cascade="all, delete-orphan")
    working_hours = relationship("GarageWorkingHours", back_populates="garage", cascade="all, delete-orphan")
    banking       = relationship("GarageBanking",      back_populates="garage", uselist=False, cascade="all, delete-orphan")
    services      = relationship("GarageService",      back_populates="garage", cascade="all, delete-orphan")
    bookings      = relationship("Booking",            back_populates="garage", cascade="all, delete-orphan")
    documents     = relationship("GarageDocument",     back_populates="garage", cascade="all, delete-orphan")


# ──────────────────────────────────────────
# GARAGE DOCUMENTS (Admin Uploads)
# ──────────────────────────────────────────

class GarageDocument(Base):
    __tablename__ = "garage_documents"

    id            = Column(Integer, primary_key=True, index=True)
    garage_id     = Column(Integer, ForeignKey("garages.id"), nullable=True)
    request_id    = Column(Integer, ForeignKey("garage_requests.id"), nullable=True)
    document_type = Column(String(50), nullable=False)  # aadhar, pan, shop_license
    file_url      = Column(Text, nullable=False)
    uploaded_at   = Column(DateTime(timezone=True), server_default=func.now())

    garage        = relationship("Garage", back_populates="documents")
    request       = relationship("GarageRequest", back_populates="documents")


# ──────────────────────────────────────────
# GARAGE LOCATION
# ──────────────────────────────────────────

class GarageLocation(Base):
    __tablename__ = "garage_locations"

    id          = Column(Integer, primary_key=True, index=True)
    garage_id   = Column(Integer, ForeignKey("garages.id"), nullable=False, unique=True)
    shop_number = Column(String(100), nullable=True)
    street      = Column(String(255), nullable=True)
    city        = Column(String(100), nullable=False, default="Ahmedabad")
    pincode     = Column(String(10), nullable=True)
    latitude    = Column(Float, nullable=True)
    longitude   = Column(Float, nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    garage      = relationship("Garage", back_populates="location")


# ──────────────────────────────────────────
# GARAGE WORKING HOURS
# ──────────────────────────────────────────

class GarageWorkingHours(Base):
    __tablename__ = "garage_working_hours"

    id          = Column(Integer, primary_key=True, index=True)
    garage_id   = Column(Integer, ForeignKey("garages.id"), nullable=False)
    day_of_week = Column(String(10), nullable=False)
    is_open     = Column(Boolean, default=True)
    open_time   = Column(Time, nullable=True)
    close_time  = Column(Time, nullable=True)

    garage      = relationship("Garage", back_populates="working_hours")


# ──────────────────────────────────────────
# GARAGE BANKING & PAYOUTS
# ──────────────────────────────────────────

class GarageBanking(Base):
    __tablename__ = "garage_banking"

    id             = Column(Integer, primary_key=True, index=True)
    garage_id      = Column(Integer, ForeignKey("garages.id"), nullable=False, unique=True)
    upi_id         = Column(String(100), nullable=True)
    account_holder = Column(String(255), nullable=True)
    bank_name      = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True)
    ifsc_code      = Column(String(20), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), onupdate=func.now())

    garage         = relationship("Garage", back_populates="banking")


# ──────────────────────────────────────────
# GARAGE SERVICES
# ──────────────────────────────────────────

class GarageService(Base):
    __tablename__ = "garage_services"

    id           = Column(Integer, primary_key=True, index=True)
    garage_id    = Column(Integer, ForeignKey("garages.id"), nullable=False)
    service_name = Column(String(100), nullable=False)
    category     = Column(String, nullable=True)
    price        = Column(Numeric(10, 2), nullable=True)
    price_type   = Column(String(20), default="fixed")  # fixed | starting | estimate | quote
    is_available = Column(Boolean, default=True)
    garage       = relationship("Garage", back_populates="services")


# ──────────────────────────────────────────
# BOOKING
# ──────────────────────────────────────────

class Booking(Base):
    __tablename__ = "bookings"

    id                     = Column(Integer, primary_key=True, index=True)
    booking_number         = Column(String(50), unique=True, index=True, nullable=True)
    slug                   = Column(String(300), unique=True, nullable=True, index=True)
    customer_id            = Column(Integer, ForeignKey("customers.id"), nullable=False)
    garage_id              = Column(Integer, ForeignKey("garages.id"), nullable=False)
    booking_type           = Column(Enum(BookingType), nullable=False)
    status                 = Column(Enum(BookingStatus), default=BookingStatus.pending)
    vehicle_type           = Column(String(50), nullable=False)
    vehicle_model          = Column(String(100), nullable=True)
    vehicle_number         = Column(String(20), nullable=True)
    service_type           = Column(String(255), nullable=True)
    description            = Column(Text, nullable=True)
    customer_lat           = Column(Float, nullable=True)
    customer_lng           = Column(Float, nullable=True)
    customer_address       = Column(String(255), nullable=True)
    requires_pick_and_drop = Column(Boolean, default=False)
    pickup_address         = Column(String(255), nullable=True)
    pickup_charge          = Column(Numeric(10, 2), nullable=True)
    estimated_amount       = Column(Numeric(10, 2), nullable=True)
    estimate_details       = Column(JSONB, nullable=True)
    estimate_status        = Column(Enum(EstimateStatus), default=EstimateStatus.not_required)
    scheduled_at           = Column(DateTime(timezone=True), nullable=True)
    responded_at           = Column(DateTime(timezone=True), nullable=True)
    started_at             = Column(DateTime(timezone=True), nullable=True)
    completed_at           = Column(DateTime(timezone=True), nullable=True)
    garage_note            = Column(Text, nullable=True)

    # OTP 1 — Known estimate confirm karne ke liye
    has_hidden_issues      = Column(Boolean, default=False)
    estimate_otp           = Column(String(6), nullable=True)
    estimate_otp_verified  = Column(Boolean, default=False)
    estimate_otp_sent_at   = Column(DateTime(timezone=True), nullable=True)

    # Additional estimate — hidden issues mile tab
    additional_estimate        = Column(Numeric(10, 2), nullable=True)
    additional_estimate_note   = Column(Text, nullable=True)
    additional_estimate_details = Column(JSONB, nullable=True)

    # OTP 2 — Additional estimate confirm karne ke liye
    additional_otp             = Column(String(6), nullable=True)
    additional_otp_verified    = Column(Boolean, default=False)
    additional_otp_sent_at     = Column(DateTime(timezone=True), nullable=True)

    final_amount           = Column(Numeric(10, 2), nullable=True)
    platform_commission    = Column(Numeric(10, 2), nullable=True)
    garage_earnings        = Column(Numeric(10, 2), nullable=True)
    payment_status         = Column(String(20), default="pending")
    created_at             = Column(DateTime(timezone=True), server_default=func.now())
    updated_at             = Column(DateTime(timezone=True), onupdate=func.now())

    customer               = relationship("Customer", back_populates="bookings")
    garage                 = relationship("Garage", back_populates="bookings")

    @property
    def customer_name(self):
        return self.customer.name if self.customer else None

    @property
    def customer_phone(self):
        return self.customer.phone if self.customer else None


# ──────────────────────────────────────────
# SOS (EMERGENCY BREAKDOWN)
# Alag booking nahi, alag tracking system
# ──────────────────────────────────────────

class SOS(Base):
    __tablename__ = "sos_requests"

    id                  = Column(Integer, primary_key=True, index=True)
    slug                = Column(String(300), unique=True, nullable=True, index=True)
    sos_number          = Column(String(50), unique=True, index=True, nullable=True)  # e.g. SOS-2026-001
    customer_id         = Column(Integer, ForeignKey("customers.id"), nullable=False)
    garage_id           = Column(Integer, ForeignKey("garages.id"), nullable=True)  # NULL jab tak accept nahi hota

    # Location
    latitude            = Column(Float, nullable=False)
    longitude           = Column(Float, nullable=False)
    address             = Column(String(255), nullable=True)
    broadcast_radius_km = Column(Float, default=2.0)

    # Vehicle Information
    vehicle_type        = Column(String(50), nullable=False)  # two_wheeler, four_wheeler
    vehicle_number      = Column(String(20), nullable=True)
    vehicle_model       = Column(String(100), nullable=True)

    # Problem Description
    description         = Column(Text, nullable=True)

    # Status
    status              = Column(Enum(SOSStatus), default=SOSStatus.broadcasting)

    # Pricing
    estimated_charge    = Column(Numeric(10, 2), nullable=True)
    visiting_charge     = Column(Numeric(10, 2), nullable=True)
    final_charge        = Column(Numeric(10, 2), nullable=True)
    platform_commission = Column(Numeric(10, 2), nullable=True)
    garage_earnings     = Column(Numeric(10, 2), nullable=True)

    # Estimate & OTP
    estimate_status     = Column(Enum(EstimateStatus), default=EstimateStatus.not_required)
    estimate_details    = Column(JSONB, nullable=True)
    estimate_otp        = Column(String(6), nullable=True)
    estimate_otp_verified = Column(Boolean, default=False)
    estimate_otp_sent_at = Column(DateTime(timezone=True), nullable=True)
    garage_note         = Column(Text, nullable=True)

    # Timestamps
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at         = Column(DateTime(timezone=True), nullable=True)
    arrived_at          = Column(DateTime(timezone=True), nullable=True)
    responded_at        = Column(DateTime(timezone=True), nullable=True)
    started_at          = Column(DateTime(timezone=True), nullable=True)
    completed_at        = Column(DateTime(timezone=True), nullable=True)
    cancelled_at        = Column(DateTime(timezone=True), nullable=True)
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer            = relationship("Customer")
    garage              = relationship("Garage")


# ──────────────────────────────────────────
# BILL / INVOICE (Bill storage for customers)
# Customer ko booking history mein bill dikhegi
# ──────────────────────────────────────────

class Bill(Base):
    __tablename__ = "bills"

    id              = Column(Integer, primary_key=True, index=True)
    booking_id      = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True)
    customer_id     = Column(Integer, ForeignKey("customers.id"), nullable=False)
    garage_id       = Column(Integer, ForeignKey("garages.id"), nullable=False)
    
    # Bill details
    bill_number     = Column(String(50), nullable=True)  # e.g., "GNM-1042-BILL"
    bill_date       = Column(DateTime(timezone=True), server_default=func.now())
    
    # Amount breakdown
    subtotal        = Column(Numeric(10, 2), nullable=False)  # Amount before tax
    tax_amount      = Column(Numeric(10, 2), default=0)       # GST/Tax
    total_amount    = Column(Numeric(10, 2), nullable=False)  # Final amount
    platform_commission = Column(Numeric(10, 2), nullable=True)
    garage_earnings     = Column(Numeric(10, 2), nullable=True)
    
    # Items (stored as JSON)
    items           = Column(JSONB, nullable=True)  # List of {item_name, price, qty}
    
    # Notes & details
    garage_name     = Column(String(255), nullable=True)
    garage_address  = Column(Text, nullable=True)
    garage_gst      = Column(String(50), nullable=True)
    
    customer_name   = Column(String(255), nullable=True)
    vehicle_info    = Column(String(255), nullable=True)
    service_type    = Column(String(255), nullable=True)
    
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    
    booking         = relationship("Booking", foreign_keys=[booking_id])
    customer        = relationship("Customer", foreign_keys=[customer_id])
    garage          = relationship("Garage", foreign_keys=[garage_id])

# ──────────────────────────────────────────
# DEFAULT SERVICES (Admin creates these)
# Mechanic ke liye pre-filled suggestions
# ──────────────────────────────────────────
 
class DefaultService(Base):
    __tablename__ = "default_services"
 
    id              = Column(Integer, primary_key=True, index=True)
    vehicle_type    = Column(String(20), nullable=False)   # two_wheeler | four_wheeler | both
    category        = Column(String(50), nullable=False)   # General Service | Repair Service | Major Repair
    service_name    = Column(String(100), nullable=False)
    suggested_price = Column(Numeric(10, 2), nullable=True)
    price_type      = Column(String(20), default="fixed")  # fixed | starting | estimate | quote
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

# ──────────────────────────────────────────
# COMMISSION RULES (Admin Sets These)
# ──────────────────────────────────────────

class CommissionRule(Base):
    __tablename__ = "commission_rules"

    id              = Column(Integer, primary_key=True, index=True)
    min_amount      = Column(Numeric(10, 2), nullable=False)
    max_amount      = Column(Numeric(10, 2), nullable=True)  # Null means infinity
    percentage      = Column(Numeric(5, 2), nullable=False)  # e.g. 10.00 for 10%
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


# ──────────────────────────────────────────
# PLATFORM PAYOUT REQUESTS (Ledger / Proofs)
# ──────────────────────────────────────────

class PlatformPayoutRequest(Base):
    __tablename__ = "platform_payout_requests"

    id             = Column(Integer, primary_key=True, index=True)
    garage_id      = Column(Integer, ForeignKey("garages.id"), nullable=False)
    amount         = Column(Numeric(10, 2), nullable=False)
    utr_number     = Column(String(50), nullable=False)
    screenshot_url = Column(Text, nullable=True)
    status         = Column(String(50), default="pending")  # pending, approved, rejected
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), onupdate=func.now())

    garage = relationship("Garage")


# ──────────────────────────────────────────
# PLATFORM ADMINS (Hashed Credentials)
# ──────────────────────────────────────────

class Admin(Base):
    __tablename__ = "admins"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())