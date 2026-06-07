from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from database import engine, Base, ensure_schema_updates, backfill_completed_bookings_and_bills, backfill_slugs
from routers import auth, garage, booking, vehicles, addresses, garage_requests, garage_auth, sos, admin_auth
from routers import default_services, commission, payout
from routers.websocket_manager import ws_manager
import re, os, json

from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
import logging

Base.metadata.create_all(bind=engine)
ensure_schema_updates()
backfill_slugs()
backfill_completed_bookings_and_bills()

last_run_date = None

async def automated_billing_cycle_task():
    global last_run_date
    while True:
        try:
            now = datetime.utcnow()
            # Run on 1st and 15th of the month
            if now.day in (1, 15):
                date_str = now.strftime("%Y-%m-%d")
                if last_run_date != date_str:
                    logging.info(f"Triggering automated 15-day billing cycle for {date_str}...")
                    from database import SessionLocal
                    from routers.payout import generate_billing_statements_internal
                    
                    db = SessionLocal()
                    try:
                        count, _ = generate_billing_statements_internal(db)
                        logging.info(f"Automated billing cycle completed. Billed {count} mechanics.")
                    except Exception as e:
                        logging.error(f"Error executing internal billing cycle: {e}")
                    finally:
                        db.close()
                        
                    last_run_date = date_str
        except Exception as e:
            logging.error(f"Error in automated billing cycle loop: {e}")
        
        # Check every 1 hour (3600 seconds)
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the background task
    task = asyncio.create_task(automated_billing_cycle_task())
    yield
    # Shutdown: Cancel the task
    task.cancel()

app = FastAPI(title="GarageNearMe API", lifespan=lifespan)

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"),             name="uploads")
app.mount("/css",     StaticFiles(directory=f"{FRONTEND_DIR}/css"), name="css")
app.mount("/js",      StaticFiles(directory=f"{FRONTEND_DIR}/js"),  name="js")

app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(auth.router,             prefix="/api/auth",             tags=["Customer Auth"])
app.include_router(booking.router,          prefix="/api/bookings",         tags=["Bookings"])
app.include_router(vehicles.router,         prefix="/api/vehicles",         tags=["Vehicles"])
app.include_router(addresses.router,        prefix="/api/addresses",        tags=["Addresses"])
app.include_router(garage_requests.router,  prefix="/api/garage-requests",  tags=["Garage Onboarding"])
app.include_router(garage_auth.router,      prefix="/api/garage-auth",      tags=["Garage Auth (OTP)"])
app.include_router(garage.router,           prefix="/api/garage",           tags=["Garage Profile"])
app.include_router(payout.router,           prefix="/api/payouts",          tags=["Payouts"])
app.include_router(sos.router,              prefix="/api/sos",              tags=["SOS"])
app.include_router(default_services.router, prefix="/api/default-services", tags=["Default Services"])
app.include_router(commission.router,       prefix="/api/commissions",      tags=["Commissions"])
app.include_router(admin_auth.router,       prefix="/api/admin-auth",       tags=["Admin Auth"])
from routers import analytics
app.include_router(analytics.router,        prefix="/api/analytics",        tags=["Analytics"])


# ── WebSocket — Mechanic ───────────────────────────────────────────────────
@app.websocket("/ws/mechanic/{garage_id}")
async def mechanic_websocket(websocket: WebSocket, garage_id: int):
    await ws_manager.connect(garage_id, websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
                continue
            try:
                data = json.loads(msg)
                msg_type = data.get("type", "")
                # WebRTC signaling — mechanic → customer relay
                if msg_type in ("webrtc_answer", "webrtc_ice", "webrtc_end"):
                    customer_id = data.get("target_customer_id")
                    if customer_id:
                        await ws_manager.send_to_customer(int(customer_id), data)
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(garage_id, websocket)


# ── WebSocket — Customer ───────────────────────────────────────────────────
@app.websocket("/ws/customer/{customer_id}")
async def customer_websocket(websocket: WebSocket, customer_id: int):
    await ws_manager.connect_customer(customer_id, websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
                continue
            try:
                data = json.loads(msg)
                msg_type = data.get("type", "")
                # WebRTC signaling — customer → mechanic relay
                if msg_type in ("webrtc_offer", "webrtc_ice", "webrtc_end"):
                    garage_id = data.get("target_garage_id")
                    if garage_id:
                        await ws_manager.send_to_garage(int(garage_id), data)
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect_customer(customer_id, websocket)


# ── Static routes ──────────────────────────────────────────────────────────
@app.get("/manifest.json", include_in_schema=False)
def serve_manifest():
    return FileResponse(os.path.join(FRONTEND_DIR, "manifest.json"))

@app.get("/favicon.ico", include_in_schema=False)
def serve_favicon():
    return FileResponse(os.path.join(FRONTEND_DIR, "assets", "favicon.ico"))

@app.get("/service-worker.js", include_in_schema=False)
def serve_sw():
    return FileResponse(os.path.join(FRONTEND_DIR, "service-worker.js"), media_type="application/javascript")

@app.get("/", include_in_schema=False)
def read_root():
    return FileResponse(os.path.join(FRONTEND_DIR, "customer", "index.html"))

@app.get("/{path:path}", include_in_schema=False)
def serve_frontend(path: str):
    has_trailing_slash = path.endswith("/")
    path = path.rstrip("/")

    if path == "customer":
        return RedirectResponse(url="/", status_code=301)
    if path.startswith("customer/"):
        return RedirectResponse(url="/" + path[len("customer/"):], status_code=301)

    if path.endswith(".html"):
        target = path[:-5]
        if target.startswith("customer/"):
            target = target[len("customer/"):]
        if target in ("admin/index", "mechanic/index"):
            section = target.split("/", 1)[0]
            return RedirectResponse(url=f"/{section}/", status_code=301)
        return RedirectResponse(url="/" + target.lstrip("/"), status_code=301)

    if not path.startswith(("admin/", "mechanic/", "api/", "css/", "js/", "uploads/")):
        for suffix in ["", ".html"]:
            f = os.path.join(FRONTEND_DIR, "customer", path + suffix)
            if os.path.isfile(f):
                return FileResponse(f)
        idx = os.path.join(FRONTEND_DIR, "customer", path, "index.html")
        if os.path.isfile(idx):
            if has_trailing_slash: return FileResponse(idx)
            return RedirectResponse(url=f"/{path}/", status_code=301)

    CUSTOMER_SLUG_ROUTES = [
        ("garage-details/",  "customer/garage-details.html"),
        ("view-bill/",       "customer/view-bill.html"),
        ("sos-tracking/",    "customer/sos-tracking.html"),
        ("booking-detail/",  "customer/booking-detail.html"),
    ]
    for slug_prefix, html_file in CUSTOMER_SLUG_ROUTES:
        if path.startswith(slug_prefix):
            remaining = path[len(slug_prefix):]
            if remaining and "/" not in remaining and "." not in remaining:
                f = os.path.join(FRONTEND_DIR, html_file)
                if os.path.isfile(f): return FileResponse(f)

    ADMIN_SLUG_ROUTES = ["admin/garage-detail/"]
    for slug_prefix in ADMIN_SLUG_ROUTES:
        if path.startswith(slug_prefix):
            remaining = path[len(slug_prefix):]
            if "/" not in remaining and "." not in remaining:
                if re.match(r'^[a-z0-9\-]+-\d+$', remaining, re.I) or re.match(r'^\d+$', remaining):
                    f = os.path.join(FRONTEND_DIR, slug_prefix.rstrip("/") + ".html")
                    if os.path.isfile(f): return FileResponse(f)

    MECHANIC_SLUG_ROUTES = [
        "mechanic/job-detail/", "mechanic/invoice/", "mechanic/edit-service/",
        "mechanic/sos-detail/", "mechanic/invoice-sos/",
    ]
    for slug_prefix in MECHANIC_SLUG_ROUTES:
        if path.startswith(slug_prefix):
            remaining = path[len(slug_prefix):]
            if "/" not in remaining and "." not in remaining and remaining:
                f = os.path.join(FRONTEND_DIR, slug_prefix.rstrip("/") + ".html")
                if os.path.isfile(f): return FileResponse(f)

    if path in ("admin/index", "mechanic/index"):
        section = path.split("/", 1)[0]
        return RedirectResponse(url=f"/{section}/", status_code=301)

    for check in [path + ".html", path, path.strip("/") + "/index.html"]:
        f = os.path.join(FRONTEND_DIR, check)
        if os.path.isfile(f):
            if check.endswith("index.html") and not has_trailing_slash:
                return RedirectResponse(url=f"/{path}/", status_code=301)
            return FileResponse(f)

    raise HTTPException(status_code=404, detail="Page not found")
