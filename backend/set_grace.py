import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
import models
from datetime import datetime, timedelta

def set_initial_grace_periods():
    db = SessionLocal()
    try:
        garages = db.query(models.Garage).filter(
            models.Garage.pending_platform_dues >= 500.0,
            models.Garage.grace_period_ends_at == None
        ).all()
        count = 0
        for g in garages:
            g.grace_period_ends_at = datetime.utcnow() + timedelta(hours=24)
            count += 1
        db.commit()
        print(f"Set grace periods for {count} garages.")
    finally:
        db.close()

if __name__ == "__main__":
    set_initial_grace_periods()
