"""Punto de entrada FastAPI."""

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.auth import router as auth_router
from app.auth.dependencies import get_current_user, require_admin
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.dependencies import get_db
from app.models import CentroTrabajo, Empleado, Empresa, Registro, Usuario
from app.routers import admin_usuarios, centros, empleados, empresas, registros
from app.templating import render


log = logging.getLogger("registro_jornada")
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title=settings.APP_NAME)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie=settings.SESSION_COOKIE_NAME,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

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


def _bootstrap_admin() -> None:
    """Crea o promueve al administrador definido en ADMIN_DNI.

    - Si ADMIN_DNI está vacío: no hace nada (modo "ya gestionado manualmente").
    - Si no existe el Usuario: lo crea con es_admin=True, sin empleado.
    - Si existe pero no es admin: lo promueve a admin y lo activa.
    - Si ya es admin: idempotente.
    """
    dni = (settings.ADMIN_DNI or "").strip().upper()
    if not dni:
        log.warning(
            "ADMIN_DNI vacío en .env — no se realizará bootstrap del administrador. "
            "Si la BBDD está vacía, nadie podrá entrar."
        )
        return
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.dni == dni).one_or_none()
        if usuario is None:
            usuario = Usuario(dni=dni, es_admin=True, activo=True, empleado_id=None)
            db.add(usuario)
            db.commit()
            log.info("Bootstrap admin: creado usuario %s con rol admin.", dni)
        elif not usuario.es_admin or not usuario.activo:
            usuario.es_admin = True
            usuario.activo = True
            db.commit()
            log.info("Bootstrap admin: usuario %s promovido a admin/activo.", dni)
    except IntegrityError:
        # Carrera entre workers — otro proceso ya lo creó. Aceptable.
        db.rollback()
    finally:
        db.close()


_bootstrap_admin()


# Routers
app.include_router(auth_router.router)
app.include_router(empresas.router)
app.include_router(centros.router)
app.include_router(empleados.router)
app.include_router(registros.router)
app.include_router(admin_usuarios.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    """Convertir 401 en redirección a /login para que la UI SSR fluya bien.

    El 403 (rol insuficiente) se deja pasar — la página estándar de error de
    FastAPI es suficiente y evita bucles si el usuario logueado intenta una
    ruta de admin sin serlo.
    """
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return RedirectResponse("/login", status_code=303)
    from fastapi.exception_handlers import http_exception_handler as default_handler
    return await default_handler(request, exc)


@app.get("/", name="home")
def home(request: Request, db: Session = Depends(get_db)) -> Response:
    """Entry point. Enruta según rol del usuario logueado."""
    current = get_current_user(request, db)
    if current is None:
        return RedirectResponse("/login", status_code=303)
    if current.es_admin:
        return RedirectResponse("/admin", status_code=303)
    return RedirectResponse("/registros", status_code=303)


@app.get("/admin", name="admin_dashboard")
def admin_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
) -> Response:
    """Dashboard de administrador con contadores."""
    return render(
        request, db, "index.html",
        app_name=settings.APP_NAME,
        current_user=current,
        total_empresas=db.query(func.count(Empresa.id)).scalar() or 0,
        total_centros=db.query(func.count(CentroTrabajo.id)).scalar() or 0,
        total_empleados=db.query(func.count(Empleado.id)).scalar() or 0,
        total_registros=db.query(func.count(Registro.id)).scalar() or 0,
        total_usuarios=db.query(func.count(Usuario.id)).scalar() or 0,
    )


@app.get("/health")
def health():
    return {"status": "ok"}
