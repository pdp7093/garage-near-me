import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
import models

def recalculate_sos_commissions():
    db = SessionLocal()
    try:
        completed_sos = db.query(models.SOS).filter(
            models.SOS.status == models.SOSStatus.completed,
            models.SOS.final_charge != None
        ).all()

        print(f"Recalculating commission for {len(completed_sos)} completed SOS requests.")

        for sos in completed_sos:
            final_amount = float(sos.final_charge)
            
            old_commission = float(sos.platform_commission) if sos.platform_commission is not None else 0.0

            commission_rule = db.query(models.CommissionRule).filter(
                models.CommissionRule.is_active == True,
                models.CommissionRule.min_amount <= final_amount,
                (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
            ).first()

            new_commission = 0.0
            if commission_rule:
                new_commission = (final_amount * float(commission_rule.percentage)) / 100.0

            garage_earnings = final_amount - new_commission

            sos.platform_commission = new_commission
            sos.garage_earnings = garage_earnings

            print(f"SOS #{sos.id}: Final = {final_amount}, Old Comm = {old_commission}, New Comm = {new_commission}")

            # Update the garage's pending platform dues
            if new_commission != old_commission:
                garage = db.query(models.Garage).filter(models.Garage.id == sos.garage_id).first()
                if garage:
                    if garage.pending_platform_dues is None:
                        garage.pending_platform_dues = 0.0
                    
                    garage.pending_platform_dues = float(garage.pending_platform_dues) - old_commission + new_commission
                    print(f"Garage #{garage.id} ({garage.name}) Dues updated to {garage.pending_platform_dues}")

        db.commit()
        print("Done recalculating.")
    finally:
        db.close()

if __name__ == "__main__":
    recalculate_sos_commissions()
