from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
from routers import auth, garage

# Saari tables create karo (agar exist nahi karti)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="GarageNearMe API")

# CORS — frontend se backend communicate kar sake
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production mein frontend domain daalna
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,   prefix="/api/auth",   tags=["Customer Auth"])
app.include_router(garage.router, prefix="/api/garage", tags=["Garage"])

@app.get("/")
def read_root():
    return {"message": "Welcome to GarageNearMe API"}