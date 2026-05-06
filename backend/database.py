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
    if "garages" not in inspector.get_table_names():
        return

    garage_columns = {column["name"] for column in inspector.get_columns("garages")}
    updates = []

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
