import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
import models

def recalculate_all_commissions():
    db = SessionLocal()
    try:
        # Reset garage dues
        garages = db.query(models.Garage).all()
        for g in garages:
            g.pending_platform_dues = 0.0

        # Recalculate Bookings
        completed_bookings = db.query(models.Booking).filter(
            models.Booking.status == models.BookingStatus.completed,
            models.Booking.final_amount != None
        ).all()
        for b in completed_bookings:
            final_amount = float(b.final_amount)
            rule = db.query(models.CommissionRule).filter(
                models.CommissionRule.is_active == True,
                models.CommissionRule.min_amount <= final_amount,
                (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
            ).first()
            comm = 0.0
            if rule:
                comm = (final_amount * float(rule.percentage)) / 100.0
            b.platform_commission = comm
            b.garage_earnings = final_amount - comm
            if b.garage:
                if b.garage.pending_platform_dues is None:
                    b.garage.pending_platform_dues = 0.0
                b.garage.pending_platform_dues += comm
            
            # Update Bill if exists
            bill = db.query(models.Bill).filter(models.Bill.booking_id == b.id).first()
            if bill:
                bill.platform_commission = comm
                bill.garage_earnings = final_amount - comm

        # Recalculate SOS
        completed_sos = db.query(models.SOS).filter(
            models.SOS.status == models.SOSStatus.completed,
            models.SOS.final_charge != None
        ).all()
        for s in completed_sos:
            final_amount = float(s.final_charge)
            rule = db.query(models.CommissionRule).filter(
                models.CommissionRule.is_active == True,
                models.CommissionRule.min_amount <= final_amount,
                (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
            ).first()
            comm = 0.0
            if rule:
                comm = (final_amount * float(rule.percentage)) / 100.0
            s.platform_commission = comm
            s.garage_earnings = final_amount - comm
            garage = db.query(models.Garage).filter(models.Garage.id == s.garage_id).first()
            if garage:
                if garage.pending_platform_dues is None:
                    garage.pending_platform_dues = 0.0
                garage.pending_platform_dues += float(comm)

        db.commit()
        print("All records updated according to NEW rules!")
    finally:
        db.close()

if __name__ == "__main__":
    recalculate_all_commissions()
