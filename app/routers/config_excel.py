"""Import/Export Excel de la configuración de planificación.

Permite gestionar en bloque, para toda la cadena, las plantillas de turno,
la dotación y los horarios de apertura. Accesible para RRHH y admin.
"""

from datetime import date

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_rrhh
from app.dependencies import get_db
from app.models import Empresa, Usuario
from app.services import excel_service
from app.templating import render


router = APIRouter(prefix="/config-excel", tags=["config-excel"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# entidad → (título, función exportar, función importar, cabeceras)
_ENTIDADES = {
    "turnos": (
        "Plantillas de turno",
        excel_service.exportar_turnos, excel_service.importar_turnos,
        excel_service._TURNO_CABECERAS,
    ),
    "dotacion": (
        "Dotación de personal",
        excel_service.exportar_dotacion, excel_service.importar_dotacion,
        excel_service._DOTACION_CABECERAS,
    ),
    "horarios": (
        "Horarios de apertura",
        excel_service.exportar_horarios, excel_service.importar_horarios,
        excel_service._HORARIO_CABECERAS,
    ),
}


def _entidad(nombre: str):
    if nombre not in _ENTIDADES:
        raise HTTPException(status_code=404, detail="Entidad no reconocida.")
    return _ENTIDADES[nombre]


@router.get("", response_class=HTMLResponse, name="config_excel_index")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    entidades = [(clave, titulo) for clave, (titulo, *_) in _ENTIDADES.items()]
    return render(
        request, db, "config_excel/index.html",
        current_user=current, entidades=entidades,
    )


@router.get("/{entidad}/exportar", name="config_excel_exportar")
def exportar(
    entidad: str,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    _titulo, exportar_fn, _imp, _cols = _entidad(entidad)
    contenido = exportar_fn(db)
    fname = f"{entidad}_{date.today().isoformat()}.xlsx"
    return Response(
        content=contenido,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{entidad}/importar", response_class=HTMLResponse, name="config_excel_importar_form")
def importar_form(
    entidad: str,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    titulo, _exp, _imp, columnas = _entidad(entidad)
    empresas = (
        db.query(Empresa).order_by(Empresa.nombre).all()
        if entidad == "horarios" else []
    )
    return render(
        request, db, "config_excel/importar.html",
        current_user=current, entidad=entidad, titulo_entidad=titulo,
        columnas=columnas, resultado=None, empresas=empresas,
    )


@router.post("/{entidad}/importar", response_class=HTMLResponse, name="config_excel_importar")
async def importar(
    entidad: str,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    archivo: UploadFile = File(...),
    empresa_id: int | None = Form(None),
):
    titulo, _exp, importar_fn, columnas = _entidad(entidad)
    contenido = await archivo.read()
    if entidad == "horarios":
        resultado = excel_service.importar_horarios(db, contenido, empresa_id)
    else:
        resultado = importar_fn(db, contenido)
    empresas = (
        db.query(Empresa).order_by(Empresa.nombre).all()
        if entidad == "horarios" else []
    )
    return render(
        request, db, "config_excel/importar.html",
        current_user=current, entidad=entidad, titulo_entidad=titulo,
        columnas=columnas, resultado=resultado, empresas=empresas,
    )
