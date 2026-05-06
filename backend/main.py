from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base, ensure_schema_updates
from routers import auth, garage, booking, vehicles, garage_requests, garage_auth

Base.metadata.create_all(bind=engine)
ensure_schema_updates()

app = FastAPI(title="GarageNearMe API")

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

# Garage
app.include_router(garage_requests.router,  prefix="/api/garage-requests",  tags=["Garage Onboarding"])
app.include_router(garage_auth.router,      prefix="/api/garage-auth",      tags=["Garage Auth (OTP)"])
app.include_router(garage.router,           prefix="/api/garage",           tags=["Garage Profile"])

@app.get("/")
def read_root():
    return {"message": "Welcome to GarageNearMe API"}
