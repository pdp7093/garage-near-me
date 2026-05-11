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
