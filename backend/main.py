from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import engine, Base, ensure_schema_updates, backfill_completed_bookings_and_bills
from routers import auth, garage, booking, vehicles, addresses, garage_requests, garage_auth, sos, admin_auth
from routers import default_services, commission, payout
import os

Base.metadata.create_all(bind=engine)
ensure_schema_updates()
backfill_completed_bookings_and_bills()

app = FastAPI(title="GarageNearMe API")

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Customer
app.include_router(auth.router,             prefix="/api/auth",             tags=["Customer Auth"])
app.include_router(booking.router,          prefix="/api/bookings",         tags=["Bookings"])
app.include_router(vehicles.router,         prefix="/api/vehicles",         tags=["Vehicles"])
app.include_router(addresses.router,        prefix="/api/addresses",        tags=["Addresses"])

# Garage
app.include_router(garage_requests.router,  prefix="/api/garage-requests",  tags=["Garage Onboarding"])
app.include_router(garage_auth.router,      prefix="/api/garage-auth",      tags=["Garage Auth (OTP)"])
app.include_router(garage.router,           prefix="/api/garage",           tags=["Garage Profile"])
app.include_router(payout.router,           prefix="/api/payouts",          tags=["Payouts"])

# SOS
app.include_router(sos.router, prefix="/api/sos", tags=["SOS"])

app.include_router(default_services.router, prefix="/api/default-services", tags=["Default Services"])
app.include_router(commission.router,       prefix="/api/commissions",      tags=["Commissions"])
app.include_router(admin_auth.router,       prefix="/api/admin-auth",       tags=["Admin Auth"])
@app.get("/")
def read_root():
    return {"message": "Welcome to GarageNearMe API"}