import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
import models

def view_rules():
    db = SessionLocal()
    rules = db.query(models.CommissionRule).all()
    for r in rules:
        print(f"Rule {r.id}: min={r.min_amount}, max={r.max_amount}, %={r.percentage}, active={r.is_active}")
    db.close()

if __name__ == "__main__":
    view_rules()
