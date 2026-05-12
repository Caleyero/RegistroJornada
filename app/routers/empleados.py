"""CRUD de empleados."""

from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import CentroTrabajo, Empleado, Empresa


router = APIRouter(prefix="/empleados", tags=["empleados"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _parse_fecha(valor: str) -> date | None:
    if not valor:
        return None
    return datetime.strptime(valor, "%Y-%m-%d").date()


@router.get("", response_class=HTMLResponse, name="empleados_list")
def list_empleados(request: Request, db: Session = Depends(get_db)):
    empleados = (
        db.query(Empleado)
        .order_by(Empleado.apellidos, Empleado.nombre)
        .all()
    )
    return templates.TemplateResponse("empleados/list.html", {
        "request": request, "empleados": empleados,
    })


@router.get("/nuevo", response_class=HTMLResponse, name="empleados_new")
def new_empleado_form(request: Request, db: Session = Depends(get_db)):
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    centros = db.query(CentroTrabajo).order_by(CentroTrabajo.nombre).all()
    return templates.TemplateResponse("empleados/form.html", {
        "request": request, "empleado": None,
        "empresas": empresas, "centros": centros,
    })


@router.post("/nuevo", name="empleados_create")
def create_empleado(
    db: Session = Depends(get_db),
    empresa_id: int = Form(...),
    centro_trabajo_id: int = Form(...),
    nombre: str = Form(...),
    apellidos: str = Form(...),
    nif: str = Form(...),
    numero_afiliacion_ss: str = Form(""),
    categoria_profesional: str = Form(""),
    tipo_contrato: str = Form(""),
    horas_semanales: float = Form(40.0),
    fecha_alta: str = Form(""),
    fecha_baja: str = Form(""),
    activo: bool = Form(False),
    email: str = Form(""),
    telefono: str = Form(""),
):
    nif_norm = nif.strip().upper()
    if db.query(Empleado).filter(Empleado.nif == nif_norm).first():
        raise HTTPException(status_code=400, detail="Ya existe un empleado con ese NIF.")
    if not db.get(Empresa, empresa_id):
        raise HTTPException(status_code=400, detail="Empresa inexistente.")
    if not db.get(CentroTrabajo, centro_trabajo_id):
        raise HTTPException(status_code=400, detail="Centro de trabajo inexistente.")
    empleado = Empleado(
        empresa_id=empresa_id,
        centro_trabajo_id=centro_trabajo_id,
        nombre=nombre.strip(),
        apellidos=apellidos.strip(),
        nif=nif_norm,
        numero_afiliacion_ss=numero_afiliacion_ss.strip() or None,
        categoria_profesional=categoria_profesional.strip() or None,
        tipo_contrato=tipo_contrato.strip() or None,
        horas_semanales=horas_semanales,
        fecha_alta=_parse_fecha(fecha_alta),
        fecha_baja=_parse_fecha(fecha_baja),
        activo=activo,
        email=email.strip() or None,
        telefono=telefono.strip() or None,
    )
    db.add(empleado)
    db.commit()
    return RedirectResponse("/empleados", status_code=303)


@router.get("/{empleado_id}/editar", response_class=HTMLResponse, name="empleados_edit")
def edit_empleado_form(empleado_id: int, request: Request, db: Session = Depends(get_db)):
    empleado = db.get(Empleado, empleado_id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    centros = db.query(CentroTrabajo).order_by(CentroTrabajo.nombre).all()
    return templates.TemplateResponse("empleados/form.html", {
        "request": request, "empleado": empleado,
        "empresas": empresas, "centros": centros,
    })


@router.post("/{empleado_id}/editar", name="empleados_update")
def update_empleado(
    empleado_id: int,
    db: Session = Depends(get_db),
    empresa_id: int = Form(...),
    centro_trabajo_id: int = Form(...),
    nombre: str = Form(...),
    apellidos: str = Form(...),
    nif: str = Form(...),
    numero_afiliacion_ss: str = Form(""),
    categoria_profesional: str = Form(""),
    tipo_contrato: str = Form(""),
    horas_semanales: float = Form(40.0),
    fecha_alta: str = Form(""),
    fecha_baja: str = Form(""),
    activo: bool = Form(False),
    email: str = Form(""),
    telefono: str = Form(""),
):
    empleado = db.get(Empleado, empleado_id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    nif_norm = nif.strip().upper()
    if nif_norm != empleado.nif and db.query(Empleado).filter(Empleado.nif == nif_norm).first():
        raise HTTPException(status_code=400, detail="Ya existe otro empleado con ese NIF.")
    empleado.empresa_id = empresa_id
    empleado.centro_trabajo_id = centro_trabajo_id
    empleado.nombre = nombre.strip()
    empleado.apellidos = apellidos.strip()
    empleado.nif = nif_norm
    empleado.numero_afiliacion_ss = numero_afiliacion_ss.strip() or None
    empleado.categoria_profesional = categoria_profesional.strip() or None
    empleado.tipo_contrato = tipo_contrato.strip() or None
    empleado.horas_semanales = horas_semanales
    empleado.fecha_alta = _parse_fecha(fecha_alta)
    empleado.fecha_baja = _parse_fecha(fecha_baja)
    empleado.activo = activo
    empleado.email = email.strip() or None
    empleado.telefono = telefono.strip() or None
    db.commit()
    return RedirectResponse("/empleados", status_code=303)


@router.post("/{empleado_id}/eliminar", name="empleados_delete")
def delete_empleado(empleado_id: int, db: Session = Depends(get_db)):
    empleado = db.get(Empleado, empleado_id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    db.delete(empleado)
    db.commit()
    return RedirectResponse("/empleados", status_code=303)
