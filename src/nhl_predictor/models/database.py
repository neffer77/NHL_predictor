"""Database connection and session management."""

import os
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from .schema import Base

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "nhl_predictor.db"


class Database:
    """Database connection manager."""

    def __init__(self, db_path: Optional[str] = None, echo: bool = False):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Uses default if not specified.
            echo: If True, log all SQL statements.
        """
        if db_path is None:
            db_path = os.environ.get("NHL_PREDICTOR_DB", str(DEFAULT_DB_PATH))

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Create engine
        if str(self.db_path) == ":memory:":
            # In-memory database for testing
            self.engine = create_engine(
                "sqlite:///:memory:",
                echo=echo,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            self.engine = create_engine(
                f"sqlite:///{self.db_path}",
                echo=echo,
                connect_args={"check_same_thread": False},
            )

        # Enable foreign keys for SQLite
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

        logger.info(f"Database initialized at {self.db_path}")

    def create_tables(self) -> None:
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created")

    def drop_tables(self) -> None:
        """Drop all database tables."""
        Base.metadata.drop_all(bind=self.engine)
        logger.info("Database tables dropped")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        Provide a transactional scope around a series of operations.

        Usage:
            with db.session_scope() as session:
                session.add(obj)
                # auto-commits on success, rolls back on exception
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# Global database instance
_db_instance: Optional[Database] = None


def get_db(db_path: Optional[str] = None, reset: bool = False) -> Database:
    """
    Get or create the global database instance.

    Args:
        db_path: Path to database file.
        reset: If True, recreate the database instance.

    Returns:
        Database instance.
    """
    global _db_instance

    if _db_instance is None or reset:
        _db_instance = Database(db_path)
        # Auto-create tables if they don't exist
        _db_instance.create_tables()

    return _db_instance


def init_db(db_path: Optional[str] = None) -> Database:
    """
    Initialize database and create tables.

    Args:
        db_path: Path to database file.

    Returns:
        Database instance with tables created.
    """
    db = get_db(db_path, reset=True)
    db.create_tables()
    return db
