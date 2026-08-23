from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{DATA_DIR / 'resume_coach.db'}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_v01_schema():
    with engine.begin() as connection:
        claim_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(claims)").fetchall()
        }
        if claim_columns and "risk_reason" not in claim_columns:
            connection.exec_driver_sql("ALTER TABLE claims ADD COLUMN risk_reason TEXT")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
