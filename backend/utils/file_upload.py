import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile


GARAGE_DOCUMENT_ROOT = Path("uploads") / "garage_documents"

DOCUMENT_CATEGORIES = {
    "profile_photo",
    "government_id",
    "banking",
    "licenses",
    "vehicle_docs",
    "other",
} 

DOCUMENT_TYPE_CATEGORY_MAP = {
    "aadhar": "government_id",
    "aadhaar": "government_id",
    "pan": "government_id",
    "id": "government_id",
    "government_id": "government_id",
    "kyc": "government_id",
    "bank": "banking",
    "banking": "banking",
    "cancelled_cheque": "banking",
    "cancelled-cheque": "banking",
    "cheque": "banking",
    "license": "licenses",
    "licence": "licenses",
    "licenses": "licenses",
    "shop_license": "licenses",
    "trade_license": "licenses",
    "certificate": "licenses",
    "vehicle": "vehicle_docs",
    "vehicle_doc": "vehicle_docs",
    "vehicle_docs": "vehicle_docs",
    "rc": "vehicle_docs",
    "insurance": "vehicle_docs",
    "profile": "profile_photo",
    "profile_photo": "profile_photo",
    "avatar": "profile_photo",
    "logo": "profile_photo",
}


def slugify_garage_name(garage_name: str | None, owner_name: str | None = None) -> str:
    """
    Build the owner folder slug from garage name first, then owner name.
    Special characters are removed, whitespace becomes hyphens.
    """
    source_name = garage_name or owner_name or "garage"
    slug = source_name.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug).strip("-")
    return slug or "garage"


def normalize_document_category(document_type: str | None) -> str:
    if not document_type:
        return "other"

    normalized = document_type.strip().lower()
    normalized = re.sub(r"[^a-z0-9_-]", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_-")

    if normalized in DOCUMENT_CATEGORIES:
        return normalized

    return DOCUMENT_TYPE_CATEGORY_MAP.get(normalized, "other")


def _safe_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if not suffix or not re.fullmatch(r"\.[a-z0-9]+", suffix):
        return ""
    return suffix


def save_garage_document(
    file: UploadFile,
    *,
    document_type: str | None = None,
    garage_name: str | None = None,
    owner_name: str | None = None,
    category: str | None = None,
) -> str:
    """
    Save a garage document under:
    uploads/garage_documents/{garage-slug}/{category}/{unique-filename}

    Returns the URL path stored in the database.
    """
    garage_slug = slugify_garage_name(garage_name, owner_name)
    document_category = normalize_document_category(category or document_type)
    upload_dir = GARAGE_DOCUMENT_ROOT / garage_slug / document_category
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{_safe_extension(file.filename)}"
    file_path = upload_dir / filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return f"/{file_path.as_posix()}"


CUSTOMER_PROFILE_ROOT = Path("uploads") / "customer_profiles"


def save_customer_profile_image(file: UploadFile, customer_id: int) -> str:
    """
    Save a customer profile image under:
    uploads/customer_profiles/{customer_id}/{unique-filename}

    Returns the URL path stored in the database.
    """
    upload_dir = CUSTOMER_PROFILE_ROOT / str(customer_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{_safe_extension(file.filename)}"
    file_path = upload_dir / filename

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return f"/{file_path.as_posix()}"
