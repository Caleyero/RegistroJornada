"""Configuración de un centro para la planificación de turnos.

Cuelga de `/centros/{id}/...` y reúne cuatro pantallas: horario de
apertura, plantillas de turno, dotación de personal y periodos no aptos
para vacaciones. Accesible para RRHH y administradores.
"""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require_rrhh
from app.dependencies import get_db
from app.models import CentroTrabajo, PeriodoNoApto, PlantillaTurno, Usuario
from app.services import turnos_service
from app.templating import render


router = APIRouter(prefix="/centros", tags=["centros-config"])


def _get_centro(db: Session, centro_id: int) -> CentroTrabajo:
    centro = db.get(CentroTrabajo, centro_id)
    if centro is None:
        raise HTTPException(status_code=404, detail="Centro no encontrado.")
    return centro


def _int0(valor) -> int:
    """Convierte un valor de formulario a entero; cadena vacía/None → 0."""
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Horario de apertura
# ---------------------------------------------------------------------------

@router.get("/{centro_id}/horario", response_class=HTMLResponse, name="centro_horario")
def horario_form(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    error: str | None = None,
):
    centro = _get_centro(db, centro_id)
    return render(
        request, db, "centros/horario.html",
        current_user=current, centro=centro,
        horario=turnos_service.cargar_horario(db, centro_id),
        dias=turnos_service.DIAS_SEMANA, error=error,
    )


@router.post("/{centro_id}/horario", name="centro_horario_guardar")
async def horario_guardar(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    centro = _get_centro(db, centro_id)
    form = await request.form()
    datos = {
        dow: {
            "cerrado": form.get(f"cerrado_{dow}") is not None,
            "apertura": (form.get(f"apertura_{dow}") or "").strip(),
            "inicio_pausa": (form.get(f"inicio_pausa_{dow}") or "").strip(),
            "fin_pausa": (form.get(f"fin_pausa_{dow}") or "").strip(),
            "cierre": (form.get(f"cierre_{dow}") or "").strip(),
        }
        for dow in range(7)
    }
    try:
        turnos_service.guardar_horario(db, centro.id, datos)
    except ValueError as exc:
        db.rollback()
        return render(
            request, db, "centros/horario.html",
            current_user=current, centro=centro,
            horario=turnos_service.cargar_horario(db, centro.id),
            dias=turnos_service.DIAS_SEMANA, error=str(exc),
        )
    return RedirectResponse(f"/centros/{centro.id}/horario", status_code=303)


# ---------------------------------------------------------------------------
# Plantillas de turno
# ---------------------------------------------------------------------------

def _render_turnos(request, db, current, centro, error=None):
    return render(
        request, db, "centros/turnos.html",
        current_user=current, centro=centro,
        turnos=turnos_service.turnos_de(db, centro.id), error=error,
    )


@router.get("/{centro_id}/turnos", response_class=HTMLResponse, name="centro_turnos")
def turnos_list(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    centro = _get_centro(db, centro_id)
    return _render_turnos(request, db, current, centro)


@router.post("/{centro_id}/turnos/nuevo", name="centro_turnos_crear")
def turno_crear(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    nombre: str = Form(...),
    hora_inicio: str = Form(...),
    hora_fin: str = Form(...),
    inicio_pausa: str = Form(""),
    fin_pausa: str = Form(""),
    activo: bool = Form(False),
    orden: int = Form(0),
):
    centro = _get_centro(db, centro_id)
    nombre = nombre.strip()
    if not nombre:
        return _render_turnos(request, db, current, centro, "El nombre del turno es obligatorio.")
    try:
        hi, hf, ip, fp = turnos_service.validar_turno(
            hora_inicio, hora_fin, inicio_pausa, fin_pausa,
        )
    except ValueError as exc:
        return _render_turnos(request, db, current, centro, str(exc))
    db.add(PlantillaTurno(
        centro_id=centro.id, nombre=nombre,
        hora_inicio=hi, hora_fin=hf, inicio_pausa=ip, fin_pausa=fp,
        activo=activo, orden=orden,
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_turnos(
            request, db, current, centro,
            f"Ya existe un turno llamado «{nombre}» en este centro.",
        )
    return RedirectResponse(f"/centros/{centro.id}/turnos", status_code=303)


@router.post("/{centro_id}/turnos/{turno_id}/editar", name="centro_turnos_editar")
def turno_editar(
    centro_id: int,
    turno_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    nombre: str = Form(...),
    hora_inicio: str = Form(...),
    hora_fin: str = Form(...),
    inicio_pausa: str = Form(""),
    fin_pausa: str = Form(""),
    activo: bool = Form(False),
    orden: int = Form(0),
):
    centro = _get_centro(db, centro_id)
    turno = db.get(PlantillaTurno, turno_id)
    if turno is None or turno.centro_id != centro.id:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    nombre = nombre.strip()
    if not nombre:
        return _render_turnos(request, db, current, centro, "El nombre del turno es obligatorio.")
    try:
        hi, hf, ip, fp = turnos_service.validar_turno(
            hora_inicio, hora_fin, inicio_pausa, fin_pausa,
        )
    except ValueError as exc:
        return _render_turnos(request, db, current, centro, str(exc))
    turno.nombre = nombre
    turno.hora_inicio = hi
    turno.hora_fin = hf
    turno.inicio_pausa = ip
    turno.fin_pausa = fp
    turno.activo = activo
    turno.orden = orden
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _render_turnos(
            request, db, current, centro,
            f"Ya existe un turno llamado «{nombre}» en este centro.",
        )
    return RedirectResponse(f"/centros/{centro.id}/turnos", status_code=303)


@router.post("/{centro_id}/turnos/{turno_id}/eliminar", name="centro_turnos_eliminar")
def turno_eliminar(
    centro_id: int,
    turno_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    centro = _get_centro(db, centro_id)
    turno = db.get(PlantillaTurno, turno_id)
    if turno is None or turno.centro_id != centro.id:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    db.delete(turno)
    db.commit()
    return RedirectResponse(f"/centros/{centro.id}/turnos", status_code=303)


# ---------------------------------------------------------------------------
# Dotación
# ---------------------------------------------------------------------------

@router.get("/{centro_id}/dotacion", response_class=HTMLResponse, name="centro_dotacion")
def dotacion_form(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    error: str | None = None,
):
    centro = _get_centro(db, centro_id)
    return render(
        request, db, "centros/dotacion.html",
        current_user=current, centro=centro,
        turnos=turnos_service.turnos_de(db, centro_id),
        dotacion=turnos_service.matriz_dotacion(db, centro_id),
        dias=turnos_service.DIAS_SEMANA, error=error,
    )


@router.post("/{centro_id}/dotacion", name="centro_dotacion_guardar")
async def dotacion_guardar(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    centro = _get_centro(db, centro_id)
    turnos = turnos_service.turnos_de(db, centro.id)
    form = await request.form()
    datos = {}
    for t in turnos:
        for dow in range(7):
            datos[(t.id, dow)] = {
                "minimo": _int0(form.get(f"min_{t.id}_{dow}")),
                "maximo": _int0(form.get(f"max_{t.id}_{dow}")),
            }
    try:
        turnos_service.guardar_dotacion(db, centro.id, datos)
    except ValueError as exc:
        db.rollback()
        return render(
            request, db, "centros/dotacion.html",
            current_user=current, centro=centro, turnos=turnos,
            dotacion=turnos_service.matriz_dotacion(db, centro.id),
            dias=turnos_service.DIAS_SEMANA, error=str(exc),
        )
    return RedirectResponse(f"/centros/{centro.id}/dotacion", status_code=303)


# ---------------------------------------------------------------------------
# Periodos no aptos para vacaciones
# ---------------------------------------------------------------------------

def _render_periodos(request, db, current, centro, error=None):
    periodos = (
        db.query(PeriodoNoApto)
        .filter(PeriodoNoApto.centro_id == centro.id)
        .order_by(PeriodoNoApto.fecha_inicio)
        .all()
    )
    return render(
        request, db, "centros/periodos_no_aptos.html",
        current_user=current, centro=centro, periodos=periodos, error=error,
    )


@router.get(
    "/{centro_id}/periodos-no-aptos",
    response_class=HTMLResponse, name="centro_periodos",
)
def periodos_list(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    centro = _get_centro(db, centro_id)
    return _render_periodos(request, db, current, centro)


@router.post("/{centro_id}/periodos-no-aptos/nuevo", name="centro_periodos_crear")
def periodo_crear(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    nombre: str = Form(...),
    fecha_inicio: str = Form(...),
    fecha_fin: str = Form(...),
):
    centro = _get_centro(db, centro_id)
    nombre = nombre.strip()
    if not nombre:
        return _render_periodos(request, db, current, centro, "El nombre es obligatorio.")
    try:
        fi = date.fromisoformat(fecha_inicio.strip())
        ff = date.fromisoformat(fecha_fin.strip())
    except ValueError:
        return _render_periodos(request, db, current, centro, "Las fechas no son válidas.")
    if ff < fi:
        return _render_periodos(
            request, db, current, centro,
            "La fecha de fin no puede ser anterior a la de inicio.",
        )
    db.add(PeriodoNoApto(
        centro_id=centro.id, nombre=nombre, fecha_inicio=fi, fecha_fin=ff,
    ))
    db.commit()
    return RedirectResponse(f"/centros/{centro.id}/periodos-no-aptos", status_code=303)


@router.post(
    "/{centro_id}/periodos-no-aptos/{periodo_id}/eliminar",
    name="centro_periodos_eliminar",
)
def periodo_eliminar(
    centro_id: int,
    periodo_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    centro = _get_centro(db, centro_id)
    periodo = db.get(PeriodoNoApto, periodo_id)
    if periodo is None or periodo.centro_id != centro.id:
        raise HTTPException(status_code=404, detail="Periodo no encontrado.")
    db.delete(periodo)
    db.commit()
    return RedirectResponse(f"/centros/{centro.id}/periodos-no-aptos", status_code=303)
