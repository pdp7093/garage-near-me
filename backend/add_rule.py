import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
import models

def add_default_rule():
    db = SessionLocal()
    try:
        if db.query(models.CommissionRule).count() == 0:
            rule = models.CommissionRule(
                min_amount=0.0,
                max_amount=None,
                percentage=10.0,
                is_active=True
            )
            db.add(rule)
            db.commit()
            print("Added default 10% commission rule!")
        else:
            print("Rules already exist.")
    finally:
        db.close()

if __name__ == "__main__":
    add_default_rule()
