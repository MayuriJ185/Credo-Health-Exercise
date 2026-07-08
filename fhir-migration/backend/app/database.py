"""Database setup. One SQLite file, one session factory, one dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL

# check_same_thread=False lets FastAPI touch the SQLite connection from the
# worker threads it uses to run our sync endpoints.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db_session():
    """FastAPI dependency: hand out a session and always close it afterwards."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
