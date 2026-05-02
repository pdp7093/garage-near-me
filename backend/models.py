from sqlalchemy import (
    Column, Integer, String, DateTime, Float,
    Boolean, ForeignKey, Text, Time, Numeric
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


# ──────────────────────────────────────────
# CUSTOMER
# ──────────────────────────────────────────

class Customer(Base):
    __tablename__ = "customers"

    id               = Column(Integer, primary_key=True, index=True)
    name             = Column(String(255), nullable=False, index=True)
    phone            = Column(String(15), unique=True, nullable=False, index=True)
    email            = Column(String(255), unique=True, nullable=False)
    hashed_password  = Column(Text, nullable=False)
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


# ──────────────────────────────────────────
# GARAGE (main table)
# ──────────────────────────────────────────

class Garage(Base):
    __tablename__ = "garages"

    id               = Column(Integer, primary_key=True, index=True)
    name             = Column(String(255), nullable=False, index=True)
    owner_name       = Column(String(255), nullable=False)
    phone            = Column(String(15), unique=True, nullable=False, index=True)
    email            = Column(String(255), unique=True, nullable=True)
    hashed_password  = Column(Text, nullable=False)

    # four_wheeler | two_wheeler | both
    garage_type      = Column(String(50), nullable=True)

    # Profile photo / logo (Cloudinary URL baad mein)
    logo_url         = Column(Text, nullable=True)

    # Status flags
    is_active        = Column(Boolean, default=True)
    is_verified      = Column(Boolean, default=False)   # admin approve karega
    is_sos_available = Column(Boolean, default=True)    # dashboard toggle

    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    location         = relationship("GarageLocation",     back_populates="garage", uselist=False, cascade="all, delete-orphan")
    working_hours    = relationship("GarageWorkingHours", back_populates="garage", cascade="all, delete-orphan")
    banking          = relationship("GarageBanking",      back_populates="garage", uselist=False, cascade="all, delete-orphan")
    services         = relationship("GarageService",      back_populates="garage", cascade="all, delete-orphan")


# ──────────────────────────────────────────
# GARAGE LOCATION
# ──────────────────────────────────────────

class GarageLocation(Base):
    __tablename__ = "garage_locations"

    id           = Column(Integer, primary_key=True, index=True)
    garage_id    = Column(Integer, ForeignKey("garages.id"), nullable=False, unique=True)
    shop_number  = Column(String(100), nullable=True)   # "Shop No. 12, ABC Complex"
    street       = Column(String(255), nullable=True)   # "S.G. Highway, Near YMCA"
    city         = Column(String(100), nullable=False, default="Ahmedabad")
    pincode      = Column(String(10), nullable=True)
    latitude     = Column(Float, nullable=True)         # GPS - baad mein
    longitude    = Column(Float, nullable=True)         # GPS - baad mein
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    garage       = relationship("Garage", back_populates="location")


# ──────────────────────────────────────────
# GARAGE WORKING HOURS
# ──────────────────────────────────────────

class GarageWorkingHours(Base):
    __tablename__ = "garage_working_hours"

    id           = Column(Integer, primary_key=True, index=True)
    garage_id    = Column(Integer, ForeignKey("garages.id"), nullable=False)

    # monday | tuesday | wednesday | thursday | friday | saturday | sunday
    day_of_week  = Column(String(10), nullable=False)
    is_open      = Column(Boolean, default=True)
    open_time    = Column(Time, nullable=True)    # 09:00
    close_time   = Column(Time, nullable=True)    # 20:00

    garage       = relationship("Garage", back_populates="working_hours")


# ──────────────────────────────────────────
# GARAGE BANKING & PAYOUTS
# ──────────────────────────────────────────

class GarageBanking(Base):
    __tablename__ = "garage_banking"

    id               = Column(Integer, primary_key=True, index=True)
    garage_id        = Column(Integer, ForeignKey("garages.id"), nullable=False, unique=True)

    upi_id           = Column(String(100), nullable=True)   # "9876543210@ybl"
    account_holder   = Column(String(255), nullable=True)
    bank_name        = Column(String(100), nullable=True)
    account_number   = Column(String(50),  nullable=True)   # encrypt later
    ifsc_code        = Column(String(20),  nullable=True)

    created_at       = Column(DateTime(timezone=True), server_default=func.now())
    updated_at       = Column(DateTime(timezone=True), onupdate=func.now())

    garage           = relationship("Garage", back_populates="banking")


# ──────────────────────────────────────────
# GARAGE SERVICES
# ──────────────────────────────────────────

class GarageService(Base):
    __tablename__ = "garage_services"

    id            = Column(Integer, primary_key=True, index=True)
    garage_id     = Column(Integer, ForeignKey("garages.id"), nullable=False)
    service_name  = Column(String(100), nullable=False)    # "Oil Change", "AC Repair"
    price         = Column(Numeric(10, 2), nullable=True)  # optional abhi
    is_available  = Column(Boolean, default=True)

    garage        = relationship("Garage", back_populates="services")