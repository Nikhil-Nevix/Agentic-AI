"""
Database session management.
Provides SQLAlchemy engine and session factory.
"""

from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import QueuePool
from app.config import settings
from loguru import logger


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Create engine with connection pooling
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=settings.debug,  # Log SQL queries in debug mode
)


# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes.
    Yields a database session and ensures cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """
    Initialize database - create all tables.
    Called on application startup if tables don't exist.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def check_db_connection() -> bool:
    """
    Verify database connectivity.
    Returns True if connection successful, False otherwise.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info(f"Database connection successful: {settings.mysql_database}")
        return True
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False


# Event listeners for connection lifecycle logging
@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Log when new database connection is established."""
    logger.debug("New database connection established")


@event.listens_for(engine, "close")
def receive_close(dbapi_conn, connection_record):
    """Log when database connection is closed."""
    logger.debug("Database connection closed")
