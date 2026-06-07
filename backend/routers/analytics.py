from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional
import models, schemas
from database import get_db
from routers.garage_requests import check_admin

router = APIRouter()

@router.get("/revenue")
def get_revenue_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    garage_id: Optional[int] = None,
    db: Session = Depends(get_db),
    x_admin_key: str = Header(None)
):
    """
    Fetch revenue analytics for a given time period and garage.
    Only considers 'completed' bookings for revenue calculation.
    """
    check_admin(x_admin_key)

    query = db.query(models.Booking).filter(
        models.Booking.status == models.BookingStatus.completed
    )

    if garage_id:
        query = query.filter(models.Booking.garage_id == garage_id)
        
    if start_date:
        try:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(models.Booking.completed_at >= dt_start)
        except ValueError:
            pass
            
    if end_date:
        try:
            dt_end = datetime.strptime(end_date, "%Y-%m-%d")
            # Include the entire end date by adding a day (effectively <= end_date 23:59:59)
            # Actually just using a time of 23:59:59 on the end_date itself
            dt_end = dt_end.replace(hour=23, minute=59, second=59)
            query = query.filter(models.Booking.completed_at <= dt_end)
        except ValueError:
            pass

    bookings = query.order_by(models.Booking.completed_at.desc()).all()

    total_revenue = sum([float(b.platform_commission or 0) for b in bookings])
    total_bookings = len(bookings)

    # Query PlatformPayoutRequests for UTR collections
    utr_query = db.query(models.PlatformPayoutRequest).filter(
        models.PlatformPayoutRequest.status == "approved"
    )
    if garage_id:
        utr_query = utr_query.filter(models.PlatformPayoutRequest.garage_id == garage_id)
    if start_date:
        try:
            dt_start = datetime.strptime(start_date, "%Y-%m-%d")
            utr_query = utr_query.filter(models.PlatformPayoutRequest.created_at >= dt_start)
        except ValueError:
            pass
    if end_date:
        try:
            dt_end = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            utr_query = utr_query.filter(models.PlatformPayoutRequest.created_at <= dt_end)
        except ValueError:
            pass
    
    total_utr_collected = sum([float(p.amount or 0) for p in utr_query.all()])

    # Detailed List
    details = []
    for b in bookings:
        details.append({
            "id": b.id,
            "slug": b.slug,
            "garage_name": b.garage.name if b.garage else "Unknown",
            "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            "total_amount": float(b.final_amount or 0),
            "platform_commission": float(b.platform_commission or 0)
        })

    # Available Garages for Dropdown Filter
    garages = db.query(models.Garage.id, models.Garage.name).filter(models.Garage.is_active == True).all()
    garage_list = [{"id": g.id, "name": g.name} for g in garages]

    return {
        "summary": {
            "total_revenue": total_revenue,
            "total_utr_collected": total_utr_collected,
            "total_bookings": total_bookings,
        },
        "bookings": details,
        "garages": garage_list
    }
