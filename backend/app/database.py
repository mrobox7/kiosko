"""SQLAlchemy engine, session factory, base class and the FastAPI session dependency."""

import os
from collections.abc import Iterator
from decimal import Decimal

from sqlalchemy import Engine, Numeric, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://menu:menu@localhost:5434/restaurant"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # connects on first use, not here
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    # every Decimal column holds exact rupees: 10 digits, 2 after the point
    type_annotation_map = {Decimal: Numeric(10, 2)}


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def create_tables(bind: Engine) -> None:
    """Create any missing tables. Existing tables are never altered."""
    # importing the models is what registers their tables
    from app.customers import models as customers  # noqa: F401
    from app.menu import models as menu  # noqa: F401
    from app.orders import models as orders  # noqa: F401

    Base.metadata.create_all(bind)
