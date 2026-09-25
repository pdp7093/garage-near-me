from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from database import engine, Base, ensure_schema_updates, backfill_completed_bookings_and_bills, backfill_slugs
from routers import auth, garage, booking, vehicles, addresses, garage_requests, garage_auth, sos, admin_auth, app_version
from routers import default_services, commission, payout
from routers.websocket_manager import ws_manager
import re, os, json
import mimetypes

# .apk files ko sahi Android package type se register karo, warna browser
# unhe generic ZIP samajh ke download kar deta hai (kyunki APK internally
# ek ZIP-based format hai)
mimetypes.add_type("application/vnd.android.package-archive", ".apk")

from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timedelta
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
            # Run on 15th and 30th of the month
            if now.day in (15, 30):
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

async def automated_sos_cleanup_task():
    while True:
        try:
            from database import SessionLocal
            import models
            from routers.websocket_manager import ws_manager
            
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                cutoff_time = now - timedelta(minutes=15)
                
                expired_soses = db.query(models.SOS).filter(
                    models.SOS.status == models.SOSStatus.broadcasting,
                    models.SOS.created_at <= cutoff_time
                ).all()
                
                for sos in expired_soses:
                    logging.info(f"Auto-cancelling expired SOS #{sos.id}")
                    sos.status = models.SOSStatus.cancelled
                    sos.cancelled_at = now
                    
                    # Notify customer
                    if sos.customer_id:
                        asyncio.create_task(ws_manager.send_to_customer(sos.customer_id, {
                            "type": "sos_cancelled",
                            "sos_id": sos.id,
                            "message": "SOS request expired after 15 minutes of inactivity."
                        }))
                        
                if expired_soses:
                    db.commit()
            except Exception as e:
                logging.error(f"Error in SOS cleanup task execution: {e}")
            finally:
                db.close()
                
        except Exception as e:
            logging.error(f"Error in automated SOS cleanup loop: {e}")
        
        # Check every 1 minute
        await asyncio.sleep(60)





async def automated_sos_retry_task():
    """
    Har 20 second check karo — broadcasting SOS ke liye jo garages abhi
    accept/reject/excluded nahi hui, unhe dobara notify karo. Aur jo
    garage 2 min se react nahi kiya, use exclude kar do (timeout).
    """
    while True:
        try:
            from database import SessionLocal
            import models
            from fcm import send_notification
            from sqlalchemy.sql import func, text

            db = SessionLocal()
            try:
                from sqlalchemy.sql import func
                from datetime import datetime, timedelta, timezone
                
                now = datetime.now(timezone.utc)
                timeout_cutoff = now - timedelta(minutes=2)
                renotify_cutoff = now - timedelta(seconds=20)

                # 1. 2-min timeout — jo garages react nahi kiye, unhe exclude karo
                timed_out = db.query(models.SOSGarageAttempt).join(
                    models.SOS, models.SOSGarageAttempt.sos_id == models.SOS.id
                ).filter(
                    models.SOS.status == models.SOSStatus.broadcasting,
                    models.SOSGarageAttempt.is_excluded == False,
                    models.SOSGarageAttempt.created_at <= timeout_cutoff
                ).all()

                for attempt in timed_out:
                    attempt.is_excluded = True
                    logging.info(f"SOS #{attempt.sos_id} — Garage #{attempt.garage_id} timed out (2 min), excluded")

                if timed_out:
                    db.commit()

                # 2. Repeat notify — jo abhi tak active hain aur last notify ko 20 sec ho gaye
                active_attempts = db.query(models.SOSGarageAttempt).join(
                    models.SOS, models.SOSGarageAttempt.sos_id == models.SOS.id
                ).filter(
                    models.SOS.status == models.SOSStatus.broadcasting,
                    models.SOSGarageAttempt.is_excluded == False,
                    models.SOSGarageAttempt.last_notified_at <= renotify_cutoff
                ).all()

                for attempt in active_attempts:
                    garage = db.query(models.Garage).filter(models.Garage.id == attempt.garage_id).first()
                    sos_request = db.query(models.SOS).filter(models.SOS.id == attempt.sos_id).first()
                    if not garage or not garage.fcm_token or not sos_request:
                        continue

                    vt_label = {"two_wheeler": "2 Wheeler", "four_wheeler": "4 Wheeler"}.get(sos_request.vehicle_type, sos_request.vehicle_type)
                    
                    dist_text = ""
                    if garage.location and garage.location.latitude and sos_request.latitude:
                        from routers.sos import haversine
                        dist = haversine(garage.location.latitude, garage.location.longitude, sos_request.latitude, sos_request.longitude)
                        dist_text = f" — {round(dist, 2)} km door"
                        
                    send_notification(
                        token=garage.fcm_token,
                        title="🚨 SOS Emergency Alert!",
                        body=f"{vt_label} breakdown{dist_text}. Pehle accept karo!",
                        data={
                            "type":   "sos_alert",
                            "sos_id": str(sos_request.id),
                            "slug":   sos_request.slug or "",
                            "screen": "sos-alerts",
                        }
                    )
                    attempt.last_notified_at = func.now()

                if active_attempts:
                    db.commit()

            except Exception as e:
                logging.error(f"Error in SOS retry task execution: {e}")
            finally:
                db.close()

        except Exception as e:
            logging.error(f"Error in automated SOS retry loop: {e}")

        await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start the background task
    task = asyncio.create_task(automated_billing_cycle_task())
    task_sos = asyncio.create_task(automated_sos_cleanup_task())
    task_sos_retry = asyncio.create_task(automated_sos_retry_task())
    yield
    # Shutdown: Cancel the task
    task.cancel()
    task_sos.cancel()
    task_sos_retry.cancel()

app = FastAPI(title="GarageNearMe API", lifespan=lifespan)

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

os.makedirs("uploads", exist_ok=True)
os.makedirs("static_downloads", exist_ok=True)
app.mount("/downloads", StaticFiles(directory="static_downloads"), name="downloads")
app.mount("/uploads", StaticFiles(directory="uploads"),             name="uploads")
app.mount("/css",     StaticFiles(directory=f"{FRONTEND_DIR}/css"), name="css")
app.mount("/js",      StaticFiles(directory=f"{FRONTEND_DIR}/js"),  name="js")
app.mount("/lang",    StaticFiles(directory=f"{FRONTEND_DIR}/lang"), name="lang")

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
app.include_router(app_version.router, prefix="/api/app-version", tags=["App Version"])

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
                if msg_type in ("webrtc_offer", "webrtc_answer", "webrtc_ice", "webrtc_end"):
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

@app.get("/", include_in_schema=False)
def read_root():
    return FileResponse(os.path.join(FRONTEND_DIR, "customer", "index.html"))

@app.get("/{path:path}", include_in_schema=False)
def serve_frontend(path: str, request: Request):
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
        target_url = "/" + target.lstrip("/")
        if request.url.query:
            target_url += "?" + request.url.query
        return RedirectResponse(url=target_url, status_code=301)

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