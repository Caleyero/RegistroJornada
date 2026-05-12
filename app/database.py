"""Conexión SQLite y declarative base.

Para concurrencia multiusuario en red local se activa el modo WAL de SQLite
en cada conexión. Esto crea dos ficheros auxiliares junto al .db principal:

    data/registro.db
    data/registro.db-wal
    data/registro.db-shm

Los tres deben incluirse en los backups (o usar `sqlite3 .backup`).

Se activa también `PRAGMA foreign_keys=ON` para que las cláusulas
`ON DELETE SET NULL` / `CASCADE` se respeten en SQLite.
"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Asegurar que el directorio del fichero SQLite existe
if settings.DATABASE_URL.startswith("sqlite:///"):
    db_path = Path(settings.DATABASE_URL.replace("sqlite:///", "", 1))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite") else {},
)


if settings.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(Engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass
