"""Gestión de vacaciones, bajas y permisos.

RRHH da de alta los periodos directamente. Antes de guardar, el sistema
valida solapamientos, cupo anual, periodos no aptos del centro e impacto
en la dotación. Accesible para RRHH y administradores.
"""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_rrhh
from app.dependencies import get_db
from app.models import CentroTrabajo, Empleado, PeriodoVacaciones, Usuario
from app.models.periodo_vacaciones import (
    TIPO_ETIQUETAS, TIPO_VACACIONES, TIPOS_VALIDOS,
)
from app.services import conflictos_service, vacaciones_service
from app.templating import render


router = APIRouter(prefix="/vacaciones", tags=["vacaciones"])


def _empleados_activos(db: Session) -> list[Empleado]:
    return (
        db.query(Empleado)
        .filter(Empleado.activo.is_(True))
        .order_by(Empleado.apellidos, Empleado.nombre)
        .all()
    )


def _render_form(request, db, current, *, modo, periodo_id, datos,
                  conflictos=None, error=None, permitir_forzar=False):
    return render(
        request, db, "vacaciones/form.html",
        current_user=current, modo=modo, periodo_id=periodo_id,
        empleados=_empleados_activos(db), datos=datos,
        tipos=[(t, TIPO_ETIQUETAS[t]) for t in
               (TIPO_VACACIONES, "baja", "permiso")],
        conflictos=conflictos, error=error, permitir_forzar=permitir_forzar,
    )


# ---------------------------------------------------------------------------
# Listado
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, name="vacaciones_list")
def list_vacaciones(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    centro_id: int = 0,
):
    q = db.query(PeriodoVacaciones).join(
        Empleado, Empleado.id == PeriodoVacaciones.empleado_id,
    )
    if centro_id:
        q = q.filter(Empleado.centro_trabajo_id == centro_id)
    periodos = q.order_by(PeriodoVacaciones.fecha_inicio.desc()).all()
    centros = db.query(CentroTrabajo).order_by(CentroTrabajo.nombre).all()
    return render(
        request, db, "vacaciones/list.html",
        current_user=current, periodos=periodos, centros=centros,
        centro_id=centro_id, tipo_etiquetas=TIPO_ETIQUETAS,
    )


# ---------------------------------------------------------------------------
# Alta
# ---------------------------------------------------------------------------

@router.get("/nuevo", response_class=HTMLResponse, name="vacaciones_new")
def new_form(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    empleado_id: int = 0,
):
    datos = {
        "empleado_id": empleado_id, "tipo": TIPO_VACACIONES,
        "fecha_inicio": "", "fecha_fin": "", "observaciones": "",
    }
    return _render_form(
        request, db, current, modo="nuevo", periodo_id=None, datos=datos,
    )


def _parse_y_validar(db, empleado_id, tipo, fecha_inicio, fecha_fin):
    """Devuelve (empleado, fi, ff) o lanza ValueError con el mensaje."""
    empleado = db.get(Empleado, empleado_id)
    if empleado is None:
        raise ValueError("Selecciona un empleado.")
    if tipo not in TIPOS_VALIDOS:
        raise ValueError("Tipo de periodo no válido.")
    try:
        fi = date.fromisoformat(fecha_inicio.strip())
        ff = date.fromisoformat(fecha_fin.strip())
    except ValueError:
        raise ValueError("Las fechas no son válidas.")
    if ff < fi:
        raise ValueError("La fecha de fin no puede ser anterior a la de inicio.")
    return empleado, fi, ff


@router.post("/nuevo", name="vacaciones_create")
def create_vacaciones(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    empleado_id: int = Form(0),
    tipo: str = Form(TIPO_VACACIONES),
    fecha_inicio: str = Form(""),
    fecha_fin: str = Form(""),
    observaciones: str = Form(""),
    forzar: bool = Form(False),
):
    datos = {
        "empleado_id": empleado_id, "tipo": tipo,
        "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
        "observaciones": observaciones,
    }
    try:
        empleado, fi, ff = _parse_y_validar(
            db, empleado_id, tipo, fecha_inicio, fecha_fin,
        )
    except ValueError as exc:
        return _render_form(request, db, current, modo="nuevo",
                            periodo_id=None, datos=datos, error=str(exc))

    conflictos = vacaciones_service.validar_periodo(db, empleado, fi, ff, tipo)
    if conflictos_service.hay_bloqueante(conflictos):
        return _render_form(request, db, current, modo="nuevo",
                            periodo_id=None, datos=datos, conflictos=conflictos,
                            error="No se puede guardar: revisa los conflictos.")
    if conflictos and not forzar:
        return _render_form(request, db, current, modo="nuevo",
                            periodo_id=None, datos=datos, conflictos=conflictos,
                            permitir_forzar=True,
                            error="Hay avisos. Revísalos y confirma si procede.")

    db.add(PeriodoVacaciones(
        empleado_id=empleado.id, fecha_inicio=fi, fecha_fin=ff, tipo=tipo,
        observaciones=observaciones.strip() or None,
    ))
    db.commit()
    return RedirectResponse("/vacaciones", status_code=303)


# ---------------------------------------------------------------------------
# Edición
# ---------------------------------------------------------------------------

@router.get("/{periodo_id}/editar", response_class=HTMLResponse, name="vacaciones_edit")
def edit_form(
    periodo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    periodo = db.get(PeriodoVacaciones, periodo_id)
    if periodo is None:
        raise HTTPException(status_code=404, detail="Periodo no encontrado.")
    datos = {
        "empleado_id": periodo.empleado_id, "tipo": periodo.tipo,
        "fecha_inicio": periodo.fecha_inicio.isoformat(),
        "fecha_fin": periodo.fecha_fin.isoformat(),
        "observaciones": periodo.observaciones or "",
    }
    return _render_form(
        request, db, current, modo="editar", periodo_id=periodo.id, datos=datos,
    )


@router.post("/{periodo_id}/editar", name="vacaciones_update")
def update_vacaciones(
    periodo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    empleado_id: int = Form(0),
    tipo: str = Form(TIPO_VACACIONES),
    fecha_inicio: str = Form(""),
    fecha_fin: str = Form(""),
    observaciones: str = Form(""),
    forzar: bool = Form(False),
):
    periodo = db.get(PeriodoVacaciones, periodo_id)
    if periodo is None:
        raise HTTPException(status_code=404, detail="Periodo no encontrado.")
    datos = {
        "empleado_id": empleado_id, "tipo": tipo,
        "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
        "observaciones": observaciones,
    }
    try:
        empleado, fi, ff = _parse_y_validar(
            db, empleado_id, tipo, fecha_inicio, fecha_fin,
        )
    except ValueError as exc:
        return _render_form(request, db, current, modo="editar",
                            periodo_id=periodo.id, datos=datos, error=str(exc))

    conflictos = vacaciones_service.validar_periodo(
        db, empleado, fi, ff, tipo, excluir_id=periodo.id,
    )
    if conflictos_service.hay_bloqueante(conflictos):
        return _render_form(request, db, current, modo="editar",
                            periodo_id=periodo.id, datos=datos,
                            conflictos=conflictos,
                            error="No se puede guardar: revisa los conflictos.")
    if conflictos and not forzar:
        return _render_form(request, db, current, modo="editar",
                            periodo_id=periodo.id, datos=datos,
                            conflictos=conflictos, permitir_forzar=True,
                            error="Hay avisos. Revísalos y confirma si procede.")

    periodo.empleado_id = empleado.id
    periodo.tipo = tipo
    periodo.fecha_inicio = fi
    periodo.fecha_fin = ff
    periodo.observaciones = observaciones.strip() or None
    db.commit()
    return RedirectResponse("/vacaciones", status_code=303)


@router.post("/{periodo_id}/eliminar", name="vacaciones_delete")
def delete_vacaciones(
    periodo_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    periodo = db.get(PeriodoVacaciones, periodo_id)
    if periodo is None:
        raise HTTPException(status_code=404, detail="Periodo no encontrado.")
    db.delete(periodo)
    db.commit()
    return RedirectResponse("/vacaciones", status_code=303)
