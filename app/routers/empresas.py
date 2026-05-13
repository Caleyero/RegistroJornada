"""CRUD de empresas (solo admin)."""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.dependencies import get_db
from app.models import Empresa
from app.services import excel_service
from app.templating import render


router = APIRouter(
    prefix="/empresas",
    tags=["empresas"],
    dependencies=[Depends(require_admin)],
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("", response_class=HTMLResponse, name="empresas_list")
def list_empresas(request: Request, db: Session = Depends(get_db)):
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    return render(request, db, "empresas/list.html", empresas=empresas)


@router.get("/nueva", response_class=HTMLResponse, name="empresas_new")
def new_empresa_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "empresas/form.html", empresa=None)


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
    return render(request, db, "empresas/form.html", empresa=empresa)


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


@router.get("/exportar", name="empresas_exportar")
def exportar_empresas(db: Session = Depends(get_db)):
    contenido = excel_service.exportar_empresas(db)
    fname = f"empresas_{date.today().isoformat()}.xlsx"
    return Response(
        content=contenido,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/importar", response_class=HTMLResponse, name="empresas_importar_form")
def importar_empresas_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "empresas/import.html", resultado=None)


@router.post("/importar", response_class=HTMLResponse, name="empresas_importar")
async def importar_empresas(
    request: Request,
    db: Session = Depends(get_db),
    archivo: UploadFile = File(...),
):
    contenido = await archivo.read()
    resultado = excel_service.importar_empresas(db, contenido)
    return render(request, db, "empresas/import.html", resultado=resultado)
