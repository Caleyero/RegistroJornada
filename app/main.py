"""Punto de entrada FastAPI."""

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine
from app.dependencies import get_db
from app.models import CentroTrabajo, Empleado, Empresa, Registro
from app.routers import centros, empleados, empresas, registros


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title=settings.APP_NAME)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Crear tablas en el primer arranque (SQLite — sin Alembic).
Base.metadata.create_all(bind=engine)

# Migración idempotente para BBDDs preexistentes: añadir columnas que no estén.
with engine.begin() as conn:
    cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(registros)")}
    if "overrides_horario" not in cols:
        conn.exec_driver_sql(
            "ALTER TABLE registros ADD COLUMN overrides_horario JSON "
            "NOT NULL DEFAULT '{}'"
        )

app.include_router(empresas.router)
app.include_router(centros.router)
app.include_router(empleados.router)
app.include_router(registros.router)


@app.get("/", response_class=HTMLResponse, name="home")
def index(request: Request, db: Session = Depends(get_db)):
    """Dashboard sencillo con contadores."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "app_name": settings.APP_NAME,
        "total_empresas": db.query(func.count(Empresa.id)).scalar() or 0,
        "total_centros": db.query(func.count(CentroTrabajo.id)).scalar() or 0,
        "total_empleados": db.query(func.count(Empleado.id)).scalar() or 0,
        "total_registros": db.query(func.count(Registro.id)).scalar() or 0,
    })


@app.get("/health")
def health():
    return {"status": "ok"}
