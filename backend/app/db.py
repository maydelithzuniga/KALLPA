from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragma(dbapi_conn, _):  # pragma: no cover
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            try:
                cur.execute("PRAGMA journal_mode=WAL")
            except Exception:  # p. ej. en el navegador (Pyodide) no hay WAL
                pass
            cur.close()
    return eng


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(eng=None) -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(eng or engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
