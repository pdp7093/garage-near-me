from sqlalchemy import (
    Column, Integer, String, DateTime, Float,
    Boolean, ForeignKey, Text, Time, Numeric, Enum
)
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

class EstimateStatus(str, enum.Enum):
    not_required = "not_required"
    pending      = "pending"
    approved     = "approved"
    rejected     = "rejected"

class GarageRequestStatus(str, enum.Enum):
    pending  = "pending"   # naya request, admin ne nahi dekha
    approved = "approved"  # admin ne approve kiya → garages table mein create
    rejected = "rejected"  # admin ne reject kiya


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
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    bookings        = relationship("Booking", back_populates="customer", cascade="all, delete-orphan")
    vehicles        = relationship("Vehicle", back_populates="customer", cascade="all, delete-orphan")


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

    # Status
    status       = Column(Enum(GarageRequestStatus), default=GarageRequestStatus.pending)

    # Admin note (rejection reason etc.)
    admin_note   = Column(Text, nullable=True)

    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())


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

    created_at           = Column(DateTime(timezone=True), server_default=func.now())
    updated_at           = Column(DateTime(timezone=True), onupdate=func.now())

    location      = relationship("GarageLocation",     back_populates="garage", uselist=False, cascade="all, delete-orphan")
    working_hours = relationship("GarageWorkingHours", back_populates="garage", cascade="all, delete-orphan")
    banking       = relationship("GarageBanking",      back_populates="garage", uselist=False, cascade="all, delete-orphan")
    services      = relationship("GarageService",      back_populates="garage", cascade="all, delete-orphan")
    bookings      = relationship("Booking",            back_populates="garage", cascade="all, delete-orphan")


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
    price        = Column(Numeric(10, 2), nullable=True)
    is_available = Column(Boolean, default=True)

    garage       = relationship("Garage", back_populates="services")


# ──────────────────────────────────────────
# BOOKING
# ──────────────────────────────────────────

class Booking(Base):
    __tablename__ = "bookings"

    id                     = Column(Integer, primary_key=True, index=True)
    customer_id            = Column(Integer, ForeignKey("customers.id"), nullable=False)
    garage_id              = Column(Integer, ForeignKey("garages.id"), nullable=False)
    booking_type           = Column(Enum(BookingType), nullable=False)
    status                 = Column(Enum(BookingStatus), default=BookingStatus.pending)
    vehicle_type           = Column(String(50), nullable=False)
    vehicle_model          = Column(String(100), nullable=True)
    vehicle_number         = Column(String(20), nullable=True)
    description            = Column(Text, nullable=True)
    customer_lat           = Column(Float, nullable=True)
    customer_lng           = Column(Float, nullable=True)
    customer_address       = Column(String(255), nullable=True)
    requires_pick_and_drop = Column(Boolean, default=False)
    pickup_address         = Column(String(255), nullable=True)
    pickup_charge          = Column(Numeric(10, 2), nullable=True)
    estimated_amount       = Column(Numeric(10, 2), nullable=True)
    estimate_status        = Column(Enum(EstimateStatus), default=EstimateStatus.not_required)
    scheduled_at           = Column(DateTime(timezone=True), nullable=True)
    responded_at           = Column(DateTime(timezone=True), nullable=True)
    started_at             = Column(DateTime(timezone=True), nullable=True)
    completed_at           = Column(DateTime(timezone=True), nullable=True)
    final_amount           = Column(Numeric(10, 2), nullable=True)
    payment_status         = Column(String(20), default="pending")
    created_at             = Column(DateTime(timezone=True), server_default=func.now())
    updated_at             = Column(DateTime(timezone=True), onupdate=func.now())

    customer               = relationship("Customer", back_populates="bookings")
    garage                 = relationship("Garage", back_populates="bookings")