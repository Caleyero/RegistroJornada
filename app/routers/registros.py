"""Asistente de registro mensual + historial."""

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Empleado, Registro
from app.services import pdf_service
from app.services.festivos import FESTIVOS_ASTURIAS


router = APIRouter(prefix="/registros", tags=["registros"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


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
# Asistente (wizard)
# ---------------------------------------------------------------------------

@router.get("/nuevo", response_class=HTMLResponse, name="registros_new")
def nuevo_registro(request: Request, db: Session = Depends(get_db)):
    empleados = (
        db.query(Empleado)
        .filter(Empleado.activo == True)  # noqa: E712
        .order_by(Empleado.apellidos, Empleado.nombre)
        .all()
    )
    hoy = date.today()
    return templates.TemplateResponse("registros/wizard.html", {
        "request": request,
        "empleados_lista": empleados,
        "festivos_asturias": FESTIVOS_ASTURIAS,
        "anio_default": hoy.year,
        "mes_default": hoy.month,
    })


@router.post("/generar", name="registros_generar")
async def generar_pdf(
    payload: RegistroPayload,
    db: Session = Depends(get_db),
):
    """Guarda el registro y devuelve el PDF."""
    empleado = db.get(Empleado, payload.empleado_id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    if not payload.dias_laborables:
        raise HTTPException(status_code=400, detail="Marca al menos un día laborable.")

    registro = _upsert_registro(db, payload)
    pdf_bytes = _generar_pdf_desde_registro(registro)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_nombre_pdf(registro)}"'},
    )


# ---------------------------------------------------------------------------
# Historial
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, name="registros_list")
def list_registros(request: Request, db: Session = Depends(get_db)):
    registros = (
        db.query(Registro)
        .join(Registro.empleado)
        .order_by(Registro.anio.desc(), Registro.mes.desc(), Empleado.apellidos)
        .all()
    )
    return templates.TemplateResponse("registros/list.html", {
        "request": request, "registros": registros,
    })


@router.get("/{registro_id}/pdf", name="registros_pdf")
def descargar_pdf(registro_id: int, db: Session = Depends(get_db)):
    registro = db.get(Registro, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    pdf_bytes = _generar_pdf_desde_registro(registro)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_nombre_pdf(registro)}"'},
    )


@router.get("/{registro_id}/editar", response_class=HTMLResponse, name="registros_edit")
def editar_registro(registro_id: int, request: Request, db: Session = Depends(get_db)):
    """Reabre el wizard precargado con un registro existente."""
    registro = db.get(Registro, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    empleados = (
        db.query(Empleado)
        .filter(Empleado.activo == True)  # noqa: E712
        .order_by(Empleado.apellidos, Empleado.nombre)
        .all()
    )
    return templates.TemplateResponse("registros/wizard.html", {
        "request": request,
        "empleados_lista": empleados,
        "festivos_asturias": FESTIVOS_ASTURIAS,
        "anio_default": registro.anio,
        "mes_default": registro.mes,
        "registro_existente": {
            "empleado_id": registro.empleado_id,
            "dias_laborables": registro.dias_laborables or [],
            "inicio_jornada": registro.inicio_jornada,
            "inicio_pausa": registro.inicio_pausa,
            "fin_pausa": registro.fin_pausa,
            "fin_jornada": registro.fin_jornada,
            "festivos": registro.festivos or {},
            "vacaciones": registro.vacaciones or [],
            "ausencias": registro.ausencias or {},
            "overrides_horario": registro.overrides_horario or {},
        },
    })


@router.post("/{registro_id}/eliminar", name="registros_delete")
def eliminar_registro(registro_id: int, db: Session = Depends(get_db)):
    registro = db.get(Registro, registro_id)
    if not registro:
        raise HTTPException(status_code=404, detail="Registro no encontrado.")
    db.delete(registro)
    db.commit()
    return RedirectResponse("/registros", status_code=303)
