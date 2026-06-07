import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:root@localhost:5432/garagenearme")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema_updates():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    updates = []

    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TYPE sosstatus ADD VALUE IF NOT EXISTS 'on_the_way';"))
            conn.execute(text("ALTER TYPE sosstatus ADD VALUE IF NOT EXISTS 'in_progress';"))
    except Exception:
        pass

    if "garages" in table_names:
        garage_columns_info = inspector.get_columns("garages")
        garage_columns = {column["name"] for column in garage_columns_info}
        garage_column_meta = {
            column["name"]: column for column in garage_columns_info
        }

        if (
            "hashed_password" in garage_columns
            and not garage_column_meta["hashed_password"].get("nullable", True)
        ):
            updates.append(
                "ALTER TABLE garages "
                "ALTER COLUMN hashed_password DROP NOT NULL"
            )

        if "offers_pick_and_drop" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN offers_pick_and_drop BOOLEAN NOT NULL DEFAULT FALSE"
            )

        if "visiting_charge" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN visiting_charge NUMERIC(10, 2) NOT NULL DEFAULT 0.0"
            )

        if "has_gst" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN has_gst BOOLEAN NOT NULL DEFAULT FALSE"
            )

        if "gst_number" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN gst_number VARCHAR(50) NULL"
            )

        if "pending_platform_dues" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN pending_platform_dues NUMERIC(10, 2) DEFAULT 0.0"
            )

        if "is_credit_locked" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN is_credit_locked BOOLEAN DEFAULT FALSE"
            )

        if "has_completed_trial" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN has_completed_trial BOOLEAN DEFAULT FALSE"
            )

        if "grace_period_ends_at" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN grace_period_ends_at TIMESTAMP WITH TIME ZONE NULL"
            )

        if "slug" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN slug VARCHAR(300) UNIQUE NULL"
            )

        if "fcm_token" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN fcm_token TEXT NULL"
            )

        if "is_sos_available" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN is_sos_available BOOLEAN NOT NULL DEFAULT TRUE"
            )

    if "garage_requests" in table_names:
        request_columns = {
            column["name"] for column in inspector.get_columns("garage_requests")
        }

        if "visit_date" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN visit_date TIMESTAMP NULL"
            )

        if "visit_notes" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN visit_notes TEXT NULL"
            )

        if "verification_notes" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN verification_notes TEXT NULL"
            )

        if "rejection_reason" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN rejection_reason TEXT NULL"
            )

        if "is_site_verified" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN is_site_verified BOOLEAN NOT NULL DEFAULT FALSE"
            )

        if "is_documents_verified" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN is_documents_verified BOOLEAN NOT NULL DEFAULT FALSE"
            )

        if "has_gst" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN has_gst BOOLEAN NOT NULL DEFAULT FALSE"
            )

        if "gst_number" not in request_columns:
            updates.append(
                "ALTER TABLE garage_requests "
                "ADD COLUMN gst_number VARCHAR(50) NULL"
            )

    if "garage_documents" in table_names:
        doc_columns = {
            column["name"] for column in inspector.get_columns("garage_documents")
        }

        if "request_id" not in doc_columns:
            updates.append(
                "ALTER TABLE garage_documents "
                "ADD COLUMN request_id INTEGER NULL REFERENCES garage_requests(id)"
            )
            updates.append(
                "ALTER TABLE garage_documents "
                "ALTER COLUMN garage_id DROP NOT NULL"
            )

    if "garage_services" in table_names:
        service_columns = {
            column["name"] for column in inspector.get_columns("garage_services")
        }

        if "category" not in service_columns:
            updates.append(
                "ALTER TABLE garage_services "
                "ADD COLUMN category VARCHAR(100)"
            )
        
        if "slug" not in service_columns:
            updates.append(
                "ALTER TABLE garage_services "
                "ADD COLUMN slug VARCHAR(300) UNIQUE NULL"
            )

        if "price_type" not in service_columns:
            updates.append(
                "ALTER TABLE garage_services "
                "ADD COLUMN price_type VARCHAR(20) NOT NULL DEFAULT 'fixed'"
            )

    if "customers" in table_names:
        customer_columns = {
            column["name"] for column in inspector.get_columns("customers")
        }

        if "profile_image" not in customer_columns:
            updates.append(
                "ALTER TABLE customers "
                "ADD COLUMN profile_image VARCHAR(500)"
            )

        if "fcm_token" not in customer_columns:
            updates.append(
                "ALTER TABLE customers "
                "ADD COLUMN fcm_token TEXT NULL"
            )

    if "bookings" in table_names:
        booking_columns = {
            column["name"] for column in inspector.get_columns("bookings")
        }

        if "service_type" not in booking_columns:
            updates.append(
                "ALTER TABLE bookings "
                "ADD COLUMN service_type VARCHAR(255)"
            )
        
        if "estimate_details" not in booking_columns:
            updates.append(
                "ALTER TABLE bookings "
                "ADD COLUMN estimate_details JSONB"
            )

        new_booking_cols = {
            "garage_note":                  "ALTER TABLE bookings ADD COLUMN garage_note TEXT NULL",
            "has_hidden_issues":            "ALTER TABLE bookings ADD COLUMN has_hidden_issues BOOLEAN NOT NULL DEFAULT FALSE",
            "estimate_otp":                 "ALTER TABLE bookings ADD COLUMN estimate_otp VARCHAR(6) NULL",
            "estimate_otp_verified":        "ALTER TABLE bookings ADD COLUMN estimate_otp_verified BOOLEAN NOT NULL DEFAULT FALSE",
            "estimate_otp_sent_at":         "ALTER TABLE bookings ADD COLUMN estimate_otp_sent_at TIMESTAMP NULL",
            "additional_estimate":          "ALTER TABLE bookings ADD COLUMN additional_estimate NUMERIC(10,2) NULL",
            "additional_estimate_note":     "ALTER TABLE bookings ADD COLUMN additional_estimate_note TEXT NULL",
            "additional_estimate_details":  "ALTER TABLE bookings ADD COLUMN additional_estimate_details JSONB NULL",
            "additional_otp":               "ALTER TABLE bookings ADD COLUMN additional_otp VARCHAR(6) NULL",
            "additional_otp_verified":      "ALTER TABLE bookings ADD COLUMN additional_otp_verified BOOLEAN NOT NULL DEFAULT FALSE",
            "additional_otp_sent_at":       "ALTER TABLE bookings ADD COLUMN additional_otp_sent_at TIMESTAMP NULL",
            "platform_commission":          "ALTER TABLE bookings ADD COLUMN platform_commission NUMERIC(10,2) NULL",
            "garage_earnings":              "ALTER TABLE bookings ADD COLUMN garage_earnings NUMERIC(10,2) NULL",
            "booking_number":               "ALTER TABLE bookings ADD COLUMN booking_number VARCHAR(50) UNIQUE NULL",
        }
        for col_name, sql in new_booking_cols.items():
            if col_name not in booking_columns:
                updates.append(sql)
                if col_name == "booking_number":
                    updates.append("UPDATE bookings SET booking_number = 'BK-OLD' || id WHERE booking_number IS NULL")
        
        if "slug" not in booking_columns:
            updates.append(
                "ALTER TABLE bookings "
                "ADD COLUMN slug VARCHAR(300) UNIQUE NULL"
            )

    if "bills" in table_names:
        bill_columns = {
            column["name"] for column in inspector.get_columns("bills")
        }
        
        new_bill_cols = {
            "platform_commission": "ALTER TABLE bills ADD COLUMN platform_commission NUMERIC(10,2) NULL",
            "garage_earnings":     "ALTER TABLE bills ADD COLUMN garage_earnings NUMERIC(10,2) NULL",
        }
        for col_name, sql in new_bill_cols.items():
            if col_name not in bill_columns:
                updates.append(sql)

    if "sos_requests" not in table_names:
        # Create SOS table if it doesn't exist
        updates.append("""
            CREATE TABLE IF NOT EXISTS sos_requests (
                id SERIAL PRIMARY KEY,
                sos_number VARCHAR(50) UNIQUE,
                slug VARCHAR(300) UNIQUE NULL,
                customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                garage_id INTEGER REFERENCES garages(id) ON DELETE SET NULL,
                latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL,
                address VARCHAR(255),
                broadcast_radius_km FLOAT DEFAULT 2.0,
                vehicle_type VARCHAR(50) NOT NULL,
                vehicle_number VARCHAR(20),
                vehicle_model VARCHAR(100),
                description TEXT,
                status VARCHAR(20) DEFAULT 'broadcasting',
                estimated_charge NUMERIC(10, 2),
                visiting_charge NUMERIC(10, 2),
                final_charge NUMERIC(10, 2),
                platform_commission NUMERIC(10, 2),
                garage_earnings NUMERIC(10, 2),
                estimate_status VARCHAR(20) DEFAULT 'not_required',
                estimate_details JSONB,
                estimate_otp VARCHAR(6),
                estimate_otp_verified BOOLEAN DEFAULT FALSE,
                estimate_otp_sent_at TIMESTAMP WITH TIME ZONE,
                garage_note TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                accepted_at TIMESTAMP WITH TIME ZONE,
                responded_at TIMESTAMP WITH TIME ZONE,
                started_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                cancelled_at TIMESTAMP WITH TIME ZONE,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        sos_columns = {
            column["name"] for column in inspector.get_columns("sos_requests")
        }
        new_sos_cols = {
            "slug":                 "ALTER TABLE sos_requests ADD COLUMN slug VARCHAR(300) UNIQUE NULL",
            "responded_at":         "ALTER TABLE sos_requests ADD COLUMN responded_at TIMESTAMP WITH TIME ZONE NULL",
            "arrived_at":           "ALTER TABLE sos_requests ADD COLUMN arrived_at TIMESTAMP WITH TIME ZONE NULL",
            "estimate_status":      "ALTER TABLE sos_requests ADD COLUMN estimate_status VARCHAR(20) DEFAULT 'not_required'",
            "estimate_details":     "ALTER TABLE sos_requests ADD COLUMN estimate_details JSONB NULL",
            "estimate_otp":         "ALTER TABLE sos_requests ADD COLUMN estimate_otp VARCHAR(6) NULL",
            "estimate_otp_verified":"ALTER TABLE sos_requests ADD COLUMN estimate_otp_verified BOOLEAN NOT NULL DEFAULT FALSE",
            "estimate_otp_sent_at": "ALTER TABLE sos_requests ADD COLUMN estimate_otp_sent_at TIMESTAMP WITH TIME ZONE NULL",
            "garage_note":          "ALTER TABLE sos_requests ADD COLUMN garage_note TEXT NULL",
        }
        for col_name, sql in new_sos_cols.items():
            if col_name not in sos_columns:
                updates.append(sql)

    if not updates:
        return

    with engine.begin() as connection:
        for statement in updates:
            connection.execute(text(statement))

def backfill_slugs():
    """Generate slugs for any garages/bookings/SOS records that are missing them."""
    import re, unicodedata
    db = SessionLocal()
    try:
        from sqlalchemy import text as _text

        def _make_slug(name, record_id):
            s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
            s = re.sub(r"[^\w\s-]", "", s).strip().lower()
            s = re.sub(r"[\s_]+", "-", s)
            s = re.sub(r"-+", "-", s)
            return f"{s}-{record_id}"

        # Backfill garage slugs
        garage_rows = db.execute(_text("SELECT id, name FROM garages WHERE slug IS NULL")).fetchall()
        for (gid, gname) in garage_rows:
            slug = _make_slug(gname or f"garage-{gid}", gid)
            db.execute(_text("UPDATE garages SET slug = :s WHERE id = :id"), {"s": slug, "id": gid})

        # Backfill booking slugs
        rows = db.execute(_text("SELECT id, booking_number FROM bookings WHERE slug IS NULL")).fetchall()
        for (bid, bnum) in rows:
            slug = _make_slug(bnum or f"bk-old-{bid}", bid)
            db.execute(_text("UPDATE bookings SET slug = :s WHERE id = :id"), {"s": slug, "id": bid})

        # Backfill SOS slugs
        sos_rows = db.execute(_text("SELECT id FROM sos_requests WHERE slug IS NULL")).fetchall()
        for (sid,) in sos_rows:
            db.execute(_text("UPDATE sos_requests SET slug = :s WHERE id = :id"), {"s": f"sos-{sid}", "id": sid})

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Backfill slugs error: {e}")
    finally:
        db.close()


def backfill_completed_bookings_and_bills():
    """
    Backfills platform_commission, garage_earnings, and Bill records 
    for completed bookings where they are currently missing,
    and updates pending platform dues for the respective garages.
    """
    import models
    db = SessionLocal()
    try:
        completed_null_bookings = db.query(models.Booking).filter(
            models.Booking.status == models.BookingStatus.completed,
            (models.Booking.platform_commission == None) | (models.Booking.garage_earnings == None)
        ).all()

        if not completed_null_bookings:
            return

        print(f"Backfill: Found {len(completed_null_bookings)} completed bookings with missing commission details.")

        for booking in completed_null_bookings:
            final_amount = float(booking.final_amount) if booking.final_amount else 0.0
            
            # Find the active commission rule
            commission_rule = db.query(models.CommissionRule).filter(
                models.CommissionRule.is_active == True,
                models.CommissionRule.min_amount <= final_amount,
                (models.CommissionRule.max_amount >= final_amount) | (models.CommissionRule.max_amount == None)
            ).first()

            platform_commission = 0.0
            if commission_rule:
                platform_commission = (final_amount * float(commission_rule.percentage)) / 100.0

            garage_earnings = final_amount - platform_commission

            booking.platform_commission = platform_commission
            booking.garage_earnings = garage_earnings

            # Generate / insert Bill record
            garage = booking.garage
            if garage:
                if garage.pending_platform_dues is None:
                    garage.pending_platform_dues = 0.0
                
                # Add the platform commission to their pending platform dues
                garage.pending_platform_dues = float(garage.pending_platform_dues) + float(platform_commission)

                # Check if a bill already exists for this booking
                existing_bill = db.query(models.Bill).filter(models.Bill.booking_id == booking.id).first()
                if not existing_bill:
                    if garage.has_gst:
                        subtotal = final_amount / 1.18
                        tax_amount = final_amount - subtotal
                    else:
                        subtotal = final_amount
                        tax_amount = 0.0

                    items = []
                    if booking.estimate_details:
                        items.extend(booking.estimate_details)
                    if booking.additional_estimate_details:
                        items.extend(booking.additional_estimate_details)
                    if booking.pickup_charge and float(booking.pickup_charge) > 0:
                        items.append({
                            "item_name": "Pick & Drop / Visiting Charge",
                            "price": float(booking.pickup_charge),
                            "qty": 1
                        })

                    garage_address = ""
                    if garage.location:
                        addr_parts = [
                            garage.location.shop_number,
                            garage.location.street,
                            garage.location.city
                        ]
                        garage_address = ", ".join([p for p in addr_parts if p])

                    vehicle_info = " • ".join([p for p in [booking.vehicle_model or booking.vehicle_type, booking.vehicle_number] if p])

                    bill = models.Bill(
                        booking_id=booking.id,
                        customer_id=booking.customer_id,
                        garage_id=booking.garage_id,
                        bill_number=f"GNM-{booking.id}-BILL",
                        subtotal=subtotal,
                        tax_amount=tax_amount,
                        total_amount=final_amount,
                        platform_commission=platform_commission,
                        garage_earnings=garage_earnings,
                        items=items,
                        garage_name=garage.name,
                        garage_address=garage_address,
                        garage_gst=garage.gst_number if garage.has_gst else None,
                        customer_name=booking.customer_name,
                        vehicle_info=vehicle_info,
                        service_type=booking.service_type or ("SOS Assistance" if booking.booking_type == models.BookingType.sos else "General Service")
                    )
                    db.add(bill)

        db.commit()
        print("Backfill: Successfully updated all completed bookings, dues, and generated missing bills.")
    except Exception as e:
        db.rollback()
        print(f"Backfill Error: {str(e)}")
    finally:
        db.close()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()