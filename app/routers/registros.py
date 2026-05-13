"""Histórico de PDFs mensuales.

El alta de un nuevo registro mensual se hace desde `/diario` (calendario
diario). Este router conserva solo el listado, la descarga del PDF guardado
y la eliminación. Las URLs antiguas del wizard redirigen al calendario.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_login
from app.dependencies import get_db
from app.models import Empleado, Registro, Usuario
from app.services import pdf_service
from app.templating import render


router = APIRouter(
    prefix="/registros",
    tags=["registros"],
    dependencies=[Depends(require_login)],
)


class RegistroPayload(BaseModel):
    """Cuerpo JSON que envía el wizard."""

    empleado_id: int
    anio: int = Field(ge=2020, le=2099)
    mes: int = Field(ge=1, le=12)
    dias_laborables: list[int] = Field(default_factory=list)
    inicio_jornada: str
    inicio_pausa: str
    fin_pausa: str
    fin_jornada: str
    festivos: dict[str, str] = Field(default_factory=dict)
    vacaciones: list[str] = Field(default_factory=list)
    ausencias: dict[str, str] = Field(default_factory=dict)
    # {fecha_iso: {inicio_jornada, inicio_pausa, fin_pausa, fin_jornada}}
    overrides_horario: dict[str, dict[str, str]] = Field(default_factory=dict)


def _ensure_owner_or_admin(registro: Registro, current: Usuario) -> None:
    """Aborta con 403 si el usuario no puede operar sobre este registro."""
    if current.es_admin:
        return
    if current.empleado_id is None or registro.empleado_id != current.empleado_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para acceder a este registro.",
        )


def _empleado_para_usuario(db: Session, current: Usuario) -> Empleado:
    """Devuelve el empleado vinculado al usuario o aborta con 403."""
    if current.empleado_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Tu usuario no está vinculado a ningún empleado. "
                "Pídele al administrador que te vincule en /admin/usuarios."
            ),
        )
    empleado = db.get(Empleado, current.empleado_id)
    if empleado is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El empleado vinculado a tu usuario ya no existe.",
        )
    return empleado


def _upsert_registro(db: Session, payload: RegistroPayload) -> Registro:
    """Crea o actualiza el registro (empleado, año, mes)."""
    existente = (
        db.query(Registro)
        .filter(
            Registro.empleado_id == payload.empleado_id,
            Registro.anio == payload.anio,
            Registro.mes == payload.mes,
        )
        .first()
    )
    if existente:
        registro = existente
    else:
        registro = Registro(
            empleado_id=payload.empleado_id,
            anio=payload.anio,
            mes=payload.mes,
        )
        db.add(registro)
    registro.dias_laborables = payload.dias_laborables
    registro.inicio_jornada = payload.inicio_jornada
    registro.inicio_pausa = payload.inicio_pausa
    registro.fin_pausa = payload.fin_pausa
    registro.fin_jornada = payload.fin_jornada
    registro.festivos = payload.festivos
    registro.vacaciones = payload.vacaciones
    registro.ausencias = payload.ausencias
    registro.overrides_horario = payload.overrides_horario
    db.commit()
    db.refresh(registro)
    return registro


def _generar_pdf_desde_registro(registro: Registro) -> bytes:
    empleado = registro.empleado
    empresa = empleado.empresa
    return pdf_service.generar_pdf_registro_mensual(
        empresa_nombre=empresa.nombre if empresa else "",
        empresa_cif=empresa.cif if empresa else "",
        empresa_ccc=(empresa.codigo_cuenta_cotizacion if empresa else "") or "",
        empleado_nombre=empleado.nombre,
        empleado_apellidos=empleado.apellidos,
        empleado_nif=empleado.nif,
        empleado_naf=empleado.numero_afiliacion_ss or "",
        anio=registro.anio,
        mes=registro.mes,
        dias_laborables=list(registro.dias_laborables or []),
        inicio_jornada=registro.inicio_jornada,
        inicio_pausa=registro.inicio_pausa,
        fin_pausa=registro.fin_pausa,
        fin_jornada=registro.fin_jornada,
        festivos=dict(registro.festivos or {}),
        vacaciones=list(registro.vacaciones or []),
        ausencias=dict(registro.ausencias or {}),
        overrides_horario=dict(registro.overrides_horario or {}),
    )


def _nombre_pdf(registro: Registro) -> str:
    nif = registro.empleado.nif if registro.empleado else "EMP"
    return f"registro_jornada_{nif}_{registro.anio}_{registro.mes:02d}.pdf"


# ---------------------------------------------------------------------------
# Compatibilidad: redirigir URLs antiguas del wizard al calendario diario
# ---------------------------------------------------------------------------

@router.get("/nuevo", name="registros_new")
def nuevo_registro_compat():
    """Redirección permanente al calendario diario (nuevo flujo unificado)."""
    return RedirectResponse("/diario", status_code=303)


@router.get("/{registro_id}/editar", name="registros_edit")
def editar_registro_compat(
    registro_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
):
    """El wizard antiguo de edición ya no existe; abrimos el calendario del mes."""
    registro = db.get(Registro, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    _ensure_owner_or_admin(registro, current)
    suffix = f"?empleado_id={registro.empleado_id}" if current.es_admin else ""
    return RedirectResponse(
        f"/diario/{registro.anio}/{registro.mes:02d}{suffix}", status_code=303,
    )


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, name="registros_list")
def list_registros(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
):
    query = db.query(Registro).join(Registro.empleado)
    aviso: str | None = None
    mi_empleado: Empleado | None = None

    if not current.es_admin:
        if current.empleado_id is None:
            aviso = (
                "Tu usuario no está vinculado a ningún empleado. "
                "Pídele al administrador que te vincule para poder generar registros."
            )
            return render(
                request, db, "registros/list.html",
                current_user=current, registros=[], aviso=aviso, mi_empleado=None,
            )
        mi_empleado = db.get(Empleado, current.empleado_id)
        query = query.filter(Registro.empleado_id == current.empleado_id)

    registros = query.order_by(
        Registro.anio.desc(), Registro.mes.desc(), Empleado.apellidos,
    ).all()
    return render(
        request, db, "registros/list.html",
        current_user=current, registros=registros,
        aviso=aviso, mi_empleado=mi_empleado,
    )


@router.get("/{registro_id}/pdf", name="registros_pdf")
def descargar_pdf(
    registro_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
):
    registro = db.get(Registro, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    _ensure_owner_or_admin(registro, current)
    pdf_bytes = _generar_pdf_desde_registro(registro)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_nombre_pdf(registro)}"'},
    )


@router.post("/{registro_id}/eliminar", name="registros_delete")
def eliminar_registro(
    registro_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
):
    registro = db.get(Registro, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    _ensure_owner_or_admin(registro, current)
    db.delete(registro)
    db.commit()
    return RedirectResponse("/registros", status_code=303)
