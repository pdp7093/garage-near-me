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

        if "grace_period_ends_at" not in garage_columns:
            updates.append(
                "ALTER TABLE garages "
                "ADD COLUMN grace_period_ends_at TIMESTAMP WITH TIME ZONE NULL"
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

    if "customers" in table_names:
        customer_columns = {
            column["name"] for column in inspector.get_columns("customers")
        }

        if "profile_image" not in customer_columns:
            updates.append(
                "ALTER TABLE customers "
                "ADD COLUMN profile_image VARCHAR(500)"
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

    if not updates:
        return

    with engine.begin() as connection:
        for statement in updates:
            connection.execute(text(statement))

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
