# =============================================================================
# FILE: App/api/database.py
# ROLE: Database connection — SQLAlchemy engine and session factory.
#
# WHAT THIS FILE DOES:
#   Sets up the PostgreSQL database connection using SQLAlchemy.
#   Provides the engine (connection pool) and session factory used
#   by all database operations throughout the application.
#
# WHO USES THIS:
#   - main.py: imports SessionLocal and engine for DB initialization
#   - All API routes: use SessionLocal() to get database sessions
#   - models.py: imports Base for ORM model definitions
#   - migrations.py: uses engine for schema changes
#
# DATABASE URL:
#   Loaded from the DATABASE_URL environment variable (set in .env).
#   Format: postgresql://user:password@host:port/dbname
# =============================================================================

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database connection URL — loaded from .env file
# No hardcoded credentials: DATABASE_URL must be provided via environment variable.
_env = os.getenv("APP_ENV", "development").lower()
_default_db = "sqlite:///halovision.db" if _env != "production" else None
DATABASE_URL = os.getenv("DATABASE_URL") or _default_db
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required in production. "
        "Example: postgresql://user:password@host:5432/dbname"
    )

# SQLAlchemy engine — manages the connection pool to PostgreSQL
engine = create_engine(DATABASE_URL)

# Session factory — each request gets its own session from this factory
SessionLocal = sessionmaker(bind=engine)

# Base class for all ORM models — all models inherit from this
Base = declarative_base()
