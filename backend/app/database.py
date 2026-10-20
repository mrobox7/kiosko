"""SQLAlchemy engine, session factory, base class and the FastAPI session dependency."""

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://menu:menu@localhost:5434/menu")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # connects on first use, not here
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
