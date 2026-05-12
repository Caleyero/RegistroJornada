"""CRUD de empresas."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Empresa


router = APIRouter(prefix="/empresas", tags=["empresas"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("", response_class=HTMLResponse, name="empresas_list")
def list_empresas(request: Request, db: Session = Depends(get_db)):
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    return templates.TemplateResponse("empresas/list.html", {
        "request": request, "empresas": empresas,
    })


@router.get("/nueva", response_class=HTMLResponse, name="empresas_new")
def new_empresa_form(request: Request):
    return templates.TemplateResponse("empresas/form.html", {
        "request": request, "empresa": None,
    })


@router.post("/nueva", name="empresas_create")
def create_empresa(
    db: Session = Depends(get_db),
    nombre: str = Form(...),
    cif: str = Form(...),
    direccion: str = Form(""),
    codigo_cuenta_cotizacion: str = Form(""),
    activa: bool = Form(False),
):
    if db.query(Empresa).filter(Empresa.cif == cif).first():
        raise HTTPException(status_code=400, detail="Ya existe una empresa con ese CIF.")
    empresa = Empresa(
        nombre=nombre.strip(),
        cif=cif.strip().upper(),
        direccion=direccion.strip() or None,
        codigo_cuenta_cotizacion=codigo_cuenta_cotizacion.strip() or None,
        activa=activa,
    )
    db.add(empresa)
    db.commit()
    return RedirectResponse("/empresas", status_code=303)


@router.get("/{empresa_id}/editar", response_class=HTMLResponse, name="empresas_edit")
def edit_empresa_form(empresa_id: int, request: Request, db: Session = Depends(get_db)):
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    return templates.TemplateResponse("empresas/form.html", {
        "request": request, "empresa": empresa,
    })


@router.post("/{empresa_id}/editar", name="empresas_update")
def update_empresa(
    empresa_id: int,
    db: Session = Depends(get_db),
    nombre: str = Form(...),
    cif: str = Form(...),
    direccion: str = Form(""),
    codigo_cuenta_cotizacion: str = Form(""),
    activa: bool = Form(False),
):
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    cif_norm = cif.strip().upper()
    if cif_norm != empresa.cif and db.query(Empresa).filter(Empresa.cif == cif_norm).first():
        raise HTTPException(status_code=400, detail="Ya existe otra empresa con ese CIF.")
    empresa.nombre = nombre.strip()
    empresa.cif = cif_norm
    empresa.direccion = direccion.strip() or None
    empresa.codigo_cuenta_cotizacion = codigo_cuenta_cotizacion.strip() or None
    empresa.activa = activa
    db.commit()
    return RedirectResponse("/empresas", status_code=303)


@router.post("/{empresa_id}/eliminar", name="empresas_delete")
def delete_empresa(empresa_id: int, db: Session = Depends(get_db)):
    empresa = db.get(Empresa, empresa_id)
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    db.delete(empresa)
    db.commit()
    return RedirectResponse("/empresas", status_code=303)
