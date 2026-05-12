"""CRUD de centros de trabajo."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import CentroTrabajo, Empresa


router = APIRouter(prefix="/centros", tags=["centros"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("", response_class=HTMLResponse, name="centros_list")
def list_centros(request: Request, db: Session = Depends(get_db)):
    centros = db.query(CentroTrabajo).order_by(CentroTrabajo.nombre).all()
    return templates.TemplateResponse("centros/list.html", {
        "request": request, "centros": centros,
    })


@router.get("/nuevo", response_class=HTMLResponse, name="centros_new")
def new_centro_form(request: Request, db: Session = Depends(get_db)):
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    return templates.TemplateResponse("centros/form.html", {
        "request": request, "centro": None, "empresas": empresas,
    })


@router.post("/nuevo", name="centros_create")
def create_centro(
    db: Session = Depends(get_db),
    empresa_id: int = Form(...),
    nombre: str = Form(...),
    direccion: str = Form(""),
    ciudad: str = Form(""),
    provincia: str = Form(""),
    codigo_postal: str = Form(""),
    codigo_centro: str = Form(""),
    activo: bool = Form(False),
):
    if not db.get(Empresa, empresa_id):
        raise HTTPException(status_code=400, detail="Empresa inexistente.")
    centro = CentroTrabajo(
        empresa_id=empresa_id,
        nombre=nombre.strip(),
        direccion=direccion.strip() or None,
        ciudad=ciudad.strip() or None,
        provincia=provincia.strip() or None,
        codigo_postal=codigo_postal.strip() or None,
        codigo_centro=codigo_centro.strip() or None,
        activo=activo,
    )
    db.add(centro)
    db.commit()
    return RedirectResponse("/centros", status_code=303)


@router.get("/{centro_id}/editar", response_class=HTMLResponse, name="centros_edit")
def edit_centro_form(centro_id: int, request: Request, db: Session = Depends(get_db)):
    centro = db.get(CentroTrabajo, centro_id)
    if not centro:
        raise HTTPException(status_code=404, detail="Centro no encontrado.")
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    return templates.TemplateResponse("centros/form.html", {
        "request": request, "centro": centro, "empresas": empresas,
    })


@router.post("/{centro_id}/editar", name="centros_update")
def update_centro(
    centro_id: int,
    db: Session = Depends(get_db),
    empresa_id: int = Form(...),
    nombre: str = Form(...),
    direccion: str = Form(""),
    ciudad: str = Form(""),
    provincia: str = Form(""),
    codigo_postal: str = Form(""),
    codigo_centro: str = Form(""),
    activo: bool = Form(False),
):
    centro = db.get(CentroTrabajo, centro_id)
    if not centro:
        raise HTTPException(status_code=404, detail="Centro no encontrado.")
    if not db.get(Empresa, empresa_id):
        raise HTTPException(status_code=400, detail="Empresa inexistente.")
    centro.empresa_id = empresa_id
    centro.nombre = nombre.strip()
    centro.direccion = direccion.strip() or None
    centro.ciudad = ciudad.strip() or None
    centro.provincia = provincia.strip() or None
    centro.codigo_postal = codigo_postal.strip() or None
    centro.codigo_centro = codigo_centro.strip() or None
    centro.activo = activo
    db.commit()
    return RedirectResponse("/centros", status_code=303)


@router.post("/{centro_id}/eliminar", name="centros_delete")
def delete_centro(centro_id: int, db: Session = Depends(get_db)):
    centro = db.get(CentroTrabajo, centro_id)
    if not centro:
        raise HTTPException(status_code=404, detail="Centro no encontrado.")
    db.delete(centro)
    db.commit()
    return RedirectResponse("/centros", status_code=303)
