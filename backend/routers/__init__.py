from sqlalchemy.orm import Session
from datetime import datetime
import models

def apply_founding_partner_if_open(garage, db: Session):
    if getattr(garage, 'is_founding_partner', False):
        return
    setting = db.query(models.PlatformSetting).filter(models.PlatformSetting.key == "founding_program_open").first()
    if setting and setting.value == "true":
        garage.is_founding_partner = True
        garage.founding_partner_since = datetime.utcnow()
