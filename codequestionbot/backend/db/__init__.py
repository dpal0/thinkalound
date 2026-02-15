from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from contextlib import contextmanager


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    return url


def get_engine():
    return create_engine(get_database_url(), pool_pre_ping=True)


def get_session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope():
    Session = get_session_factory()
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
