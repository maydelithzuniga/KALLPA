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
    eng = eng or engine
    Base.metadata.create_all(eng)
    _add_missing_columns(eng)


def _add_missing_columns(eng) -> None:
    """Migración mínima: agrega columnas nuevas (con valor por defecto) a tablas que ya existen.
    Así una base que ya tiene datos (PostgreSQL en Render) se actualiza sin borrar nada."""
    from sqlalchemy import inspect, text
    insp = inspect(eng)
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ctype = col.type.compile(dialect=eng.dialect)
                default = ""
                if col.server_default is not None:
                    default = f" DEFAULT '{col.server_default.arg}'"
                elif col.nullable is False:
                    continue   # sin valor por defecto no se puede agregar a filas existentes
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ctype}{default}'))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
