from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
import models
from database import get_db

router = APIRouter()

# ──────────────────────────────────────────
# APP VERSION CONFIG
# Jab bhi naya APK build karke website pe upload karo, yahan version
# number update karo aur download_url sahi rakho. App khulte hi
# mechanic app ye check karega aur agar purana version ho to update
# banner dikhayega.
# ──────────────────────────────────────────

DEFAULT_SETTINGS = {
    "mechanic_latest_version_code": "1",
    "mechanic_min_version_code": "1",
    "mechanic_apk_url": "",
    "mechanic_update_message": "Naya update aaya hai, kripya app update karein."
}

def safe_int(val, default=1):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

@router.get("/version")
@router.get("/app/version")
def get_app_version(app: str = Query("mechanic"), db: Session = Depends(get_db)):
    keys = [
        f"{app}_latest_version_code",
        f"{app}_min_version_code",
        f"{app}_apk_url",
        f"{app}_update_message"
    ]
    rows = db.query(models.PlatformSetting).filter(models.PlatformSetting.key.in_(keys)).all()
    settings = {r.key: (r.value or "") for r in rows}

    latest_code = safe_int(settings.get(f"{app}_latest_version_code"), 1)
    min_code = safe_int(settings.get(f"{app}_min_version_code"), 1)
    apk_url = settings.get(f"{app}_apk_url", "")
    message = settings.get(f"{app}_update_message", DEFAULT_SETTINGS["mechanic_update_message"])

    return {
        "latest_version_code": latest_code,
        "min_version_code": min_code,
        "apk_url": apk_url,
        "message": message
    }

@router.get("/mechanic-latest")
def get_latest_mechanic_version(db: Session = Depends(get_db)):
    """
    Mechanic app is\u0940 se check karta hai app khulte hi ki naya
    version available hai ya nahi.
    """
    rows = db.query(models.PlatformSetting).filter(models.PlatformSetting.key.in_([
        "mechanic_latest_version_code",
        "mechanic_min_version_code",
        "mechanic_apk_url",
        "mechanic_update_message"
    ])).all()
    settings = {r.key: (r.value or "") for r in rows}
    latest_code = safe_int(settings.get("mechanic_latest_version_code"), 1)
    apk_url = settings.get("mechanic_apk_url", "") or "https://garagenearme.net/downloads/gnm-mechanic-latest.apk"

    return {
        "latest_version": str(latest_code) + ".0",
        "download_url": apk_url,
        "latest_version_code": latest_code,
        "min_version_code": safe_int(settings.get("mechanic_min_version_code"), 1),
        "apk_url": apk_url,
        "message": settings.get("mechanic_update_message", DEFAULT_SETTINGS["mechanic_update_message"])
    }
