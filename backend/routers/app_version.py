from fastapi import APIRouter

router = APIRouter()

# ──────────────────────────────────────────
# APP VERSION CONFIG
# Jab bhi naya APK build karke website pe upload karo, yahan version
# number update karo aur download_url sahi rakho. App khulte hi
# mechanic app ye check karega aur agar purana version ho to update
# banner dikhayega.
# ──────────────────────────────────────────

LATEST_MECHANIC_APP_VERSION = "1.0"
MECHANIC_APP_DOWNLOAD_URL = "https://garagenearme.net/downloads/gnm-mechanic-latest.apk"


@router.get("/mechanic-latest")
def get_latest_mechanic_version():
    """
    Mechanic app is\u0940 se check karta hai app khulte hi ki naya
    version available hai ya nahi.
    """
    return {
        "latest_version": LATEST_MECHANIC_APP_VERSION,
        "download_url": MECHANIC_APP_DOWNLOAD_URL
    }
