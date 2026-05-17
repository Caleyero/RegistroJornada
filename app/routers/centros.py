"""CRUD de centros de trabajo (solo admin)."""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin, require_rrhh
from app.dependencies import get_db
from app.models import CentroTrabajo, Empresa
from app.services import excel_service
from app.templating import render


# El listado de centros lo pueden ver también RRHH (para entrar a la
# configuración de turnos/dotación); el alta/edición/borrado del centro y
# el import/export siguen siendo exclusivos del administrador.
router = APIRouter(prefix="/centros", tags=["centros"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_ADMIN = [Depends(require_admin)]


@router.get(
    "", response_class=HTMLResponse, name="centros_list",
    dependencies=[Depends(require_rrhh)],
)
def list_centros(request: Request, db: Session = Depends(get_db)):
    centros = db.query(CentroTrabajo).order_by(CentroTrabajo.nombre).all()
    return render(request, db, "centros/list.html", centros=centros)


@router.get("/nuevo", response_class=HTMLResponse, name="centros_new", dependencies=_ADMIN)
def new_centro_form(request: Request, db: Session = Depends(get_db)):
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    return render(request, db, "centros/form.html", centro=None, empresas=empresas)


@router.post("/nuevo", name="centros_create", dependencies=_ADMIN)
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


@router.get(
    "/{centro_id}/editar", response_class=HTMLResponse, name="centros_edit",
    dependencies=_ADMIN,
)
def edit_centro_form(centro_id: int, request: Request, db: Session = Depends(get_db)):
    centro = db.get(CentroTrabajo, centro_id)
    if not centro:
        raise HTTPException(status_code=404, detail="Centro no encontrado.")
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    return render(request, db, "centros/form.html", centro=centro, empresas=empresas)


@router.post("/{centro_id}/editar", name="centros_update", dependencies=_ADMIN)
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


@router.post("/{centro_id}/eliminar", name="centros_delete", dependencies=_ADMIN)
def delete_centro(centro_id: int, db: Session = Depends(get_db)):
    centro = db.get(CentroTrabajo, centro_id)
    if not centro:
        raise HTTPException(status_code=404, detail="Centro no encontrado.")
    db.delete(centro)
    db.commit()
    return RedirectResponse("/centros", status_code=303)


@router.get("/exportar", name="centros_exportar", dependencies=_ADMIN)
def exportar_centros(db: Session = Depends(get_db)):
    contenido = excel_service.exportar_centros(db)
    fname = f"centros_{date.today().isoformat()}.xlsx"
    return Response(
        content=contenido,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get(
    "/importar", response_class=HTMLResponse, name="centros_importar_form",
    dependencies=_ADMIN,
)
def importar_centros_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "centros/import.html", resultado=None)


@router.post(
    "/importar", response_class=HTMLResponse, name="centros_importar",
    dependencies=_ADMIN,
)
async def importar_centros(
    request: Request,
    db: Session = Depends(get_db),
    archivo: UploadFile = File(...),
):
    contenido = await archivo.read()
    resultado = excel_service.importar_centros(db, contenido)
    return render(request, db, "centros/import.html", resultado=resultado)
