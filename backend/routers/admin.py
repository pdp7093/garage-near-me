from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.sql import func
import models
from database import get_db
from pydantic import BaseModel
from routers.garage_requests import check_admin

router = APIRouter()

class FoundingProgramUpdate(BaseModel):
    open: bool

class FoundingPartnerUpdate(BaseModel):
    value: bool

@router.get("/settings/founding-program")
def get_founding_program(
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    check_admin(x_admin_key)
    setting = db.query(models.PlatformSetting).filter(models.PlatformSetting.key == "founding_program_open").first()
    is_open = setting.value == "true" if setting else False
    count = db.query(models.Garage).filter(models.Garage.is_founding_partner == True).count()
    return {"open": is_open, "count": count}

@router.patch("/settings/founding-program")
def update_founding_program(
    body: FoundingProgramUpdate,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    check_admin(x_admin_key)
    is_open = body.open
    setting = db.query(models.PlatformSetting).filter(models.PlatformSetting.key == "founding_program_open").first()
    if not setting:
        setting = models.PlatformSetting(key="founding_program_open", value="true" if is_open else "false")
        db.add(setting)
    else:
        setting.value = "true" if is_open else "false"
    db.commit()
    count = db.query(models.Garage).filter(models.Garage.is_founding_partner == True).count()
    return {"open": is_open, "count": count}

@router.patch("/garages/{garage_id}/founding-partner")
def update_garage_founding_partner(
    garage_id: int,
    body: FoundingPartnerUpdate,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    check_admin(x_admin_key)
    g = db.query(models.Garage).filter(models.Garage.id == garage_id).first()
    if not g:
        raise HTTPException(status_code=404, detail="Garage not found")
    val = body.value
    g.is_founding_partner = val
    g.founding_partner_since = func.now() if val else None
    db.commit()
    db.refresh(g)
    return {"message": "Success", "is_founding_partner": g.is_founding_partner}


class AppVersionUpdate(BaseModel):
    latest_version_code: int
    min_version_code: int
    apk_url: str = ""
    message: str = "Naya update aaya hai, kripya app update karein."


@router.get("/app-version")
def get_admin_app_version(
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    check_admin(x_admin_key)
    keys = [
        "mechanic_latest_version_code",
        "mechanic_min_version_code",
        "mechanic_apk_url",
        "mechanic_update_message"
    ]
    rows = db.query(models.PlatformSetting).filter(models.PlatformSetting.key.in_(keys)).all()
    settings = {r.key: (r.value or "") for r in rows}

    def _to_int(val, default=1):
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    return {
        "latest_version_code": _to_int(settings.get("mechanic_latest_version_code"), 1),
        "min_version_code": _to_int(settings.get("mechanic_min_version_code"), 1),
        "apk_url": settings.get("mechanic_apk_url", ""),
        "message": settings.get("mechanic_update_message", "Naya update aaya hai, kripya app update karein.")
    }


@router.post("/app-version")
def update_admin_app_version(
    body: AppVersionUpdate,
    x_admin_key: str = Header(None),
    db: Session = Depends(get_db)
):
    check_admin(x_admin_key)

    if body.min_version_code > body.latest_version_code:
        raise HTTPException(
            status_code=400,
            detail="Minimum version code cannot be greater than latest version code"
        )

    apk_url = (body.apk_url or "").strip()
    if apk_url and not apk_url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail="APK URL must be empty or start with https://"
        )

    updates = {
        "mechanic_latest_version_code": str(body.latest_version_code),
        "mechanic_min_version_code": str(body.min_version_code),
        "mechanic_apk_url": apk_url,
        "mechanic_update_message": (body.message or "Naya update aaya hai, kripya app update karein.").strip()
    }

    for k, v in updates.items():
        s = db.query(models.PlatformSetting).filter(models.PlatformSetting.key == k).first()
        if not s:
            s = models.PlatformSetting(key=k, value=v)
            db.add(s)
        else:
            s.value = v
    db.commit()

    return {
        "latest_version_code": body.latest_version_code,
        "min_version_code": body.min_version_code,
        "apk_url": apk_url,
        "message": updates["mechanic_update_message"],
        "success": True
    }

