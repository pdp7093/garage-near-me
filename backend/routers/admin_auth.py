from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from datetime import timedelta
from jose import jwt, JWTError
import models, schemas
from database import get_db
from routers.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

router = APIRouter()

def get_current_admin(
    x_admin_key: str = Header(None),
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    token = x_admin_key
    if not token and authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials:
            token = credentials

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin key required"
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        if not email or role != "admin":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin credentials"
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token"
        )
    
    admin = db.query(models.Admin).filter(models.Admin.email == email).first()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found"
        )
    return admin

@router.get("/has-admin")
def has_admin(db: Session = Depends(get_db)):
    count = db.query(models.Admin).count()
    return {"has_admin": count > 0}

@router.post("/setup", response_model=schemas.AdminResponse, status_code=status.HTTP_201_CREATED)
def setup_superadmin(admin_data: schemas.AdminCreate, db: Session = Depends(get_db)):
    # Only allow if there are 0 admins in the DB
    count = db.query(models.Admin).count()
    if count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Superadmin has already been set up"
        )
    
    hashed_password = get_password_hash(admin_data.password)
    new_admin = models.Admin(
        email=admin_data.email,
        hashed_password=hashed_password
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin

@router.post("/login")
def login_admin(login_data: schemas.AdminLoginRequest, db: Session = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.email == login_data.email).first()
    if not admin or not verify_password(login_data.password, admin.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": admin.email, "role": "admin"},
        expires_delta=access_token_expires
    )
    return {"access_token": token, "token_type": "bearer"}

@router.post("/create", response_model=schemas.AdminResponse, status_code=status.HTTP_201_CREATED)
def create_subadmin(
    new_admin_data: schemas.AdminCreate,
    current_admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    # Check if admin already exists
    existing = db.query(models.Admin).filter(models.Admin.email == new_admin_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An administrator with this email already exists"
        )
    
    hashed_password = get_password_hash(new_admin_data.password)
    new_admin = models.Admin(
        email=new_admin_data.email,
        hashed_password=hashed_password
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin

@router.get("/all", response_model=list[schemas.AdminResponse])
def get_all_admins(
    current_admin: models.Admin = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    return db.query(models.Admin).all()
