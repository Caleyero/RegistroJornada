"""CRUD de empleados (solo admin)."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.dependencies import get_db
from app.models import CentroTrabajo, Empleado, Empresa
from app.services import excel_service
from app.templating import render


router = APIRouter(
    prefix="/empleados",
    tags=["empleados"],
    dependencies=[Depends(require_admin)],
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _parse_fecha(valor: str) -> date | None:
    if not valor:
        return None
    return datetime.strptime(valor, "%Y-%m-%d").date()


def _horario_o_none(valor: str) -> str | None:
    """Devuelve la cadena 'HH:MM' o None si esta vacia."""
    v = (valor or "").strip()
    return v or None


def _dias_o_none(dias: list[int]) -> list[int] | None:
    """Devuelve la lista filtrada a 0..6 o None si esta vacia."""
    if not dias:
        return None
    norm = sorted({int(d) for d in dias if 0 <= int(d) <= 6})
    return norm or None


@router.get("", response_class=HTMLResponse, name="empleados_list")
def list_empleados(request: Request, db: Session = Depends(get_db)):
    empleados = (
        db.query(Empleado)
        .order_by(Empleado.apellidos, Empleado.nombre)
        .all()
    )
    return render(request, db, "empleados/list.html", empleados=empleados)


@router.get("/nuevo", response_class=HTMLResponse, name="empleados_new")
def new_empleado_form(request: Request, db: Session = Depends(get_db)):
    empresas = db.query(Empresa).order_by(Empresa.nombre).all()
    centros = db.query(CentroTrabajo).order_by(CentroTrabajo.nombre).all()
    return render(
        request, db, "empleados/form.html",
        empleado=None, empresas=empresas, centros=centros,
    )


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
    inicio_jornada: str = Form(""),
    inicio_pausa: str = Form(""),
    fin_pausa: str = Form(""),
    fin_jornada: str = Form(""),
    dias_laborables_habituales: list[int] = Form(default=[]),
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
        inicio_jornada=_horario_o_none(inicio_jornada),
        inicio_pausa=_horario_o_none(inicio_pausa),
        fin_pausa=_horario_o_none(fin_pausa),
        fin_jornada=_horario_o_none(fin_jornada),
        dias_laborables_habituales=_dias_o_none(dias_laborables_habituales),
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
    return render(
        request, db, "empleados/form.html",
        empleado=empleado, empresas=empresas, centros=centros,
    )


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
    inicio_jornada: str = Form(""),
    inicio_pausa: str = Form(""),
    fin_pausa: str = Form(""),
    fin_jornada: str = Form(""),
    dias_laborables_habituales: list[int] = Form(default=[]),
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
    empleado.inicio_jornada = _horario_o_none(inicio_jornada)
    empleado.inicio_pausa = _horario_o_none(inicio_pausa)
    empleado.fin_pausa = _horario_o_none(fin_pausa)
    empleado.fin_jornada = _horario_o_none(fin_jornada)
    empleado.dias_laborables_habituales = _dias_o_none(dias_laborables_habituales)
    db.commit()
    return RedirectResponse("/empleados", status_code=303)


@router.post("/{empleado_id}/eliminar", name="empleados_delete")
def delete_empleado(empleado_id: int, db: Session = Depends(get_db)):
    empleado = db.get(Empleado, empleado_id)
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    if empleado.usuario is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "El empleado tiene un usuario vinculado. "
                "Elimina o desvincula primero el usuario en /admin/usuarios."
            ),
        )
    db.delete(empleado)
    db.commit()
    return RedirectResponse("/empleados", status_code=303)


@router.get("/exportar", name="empleados_exportar")
def exportar_empleados(db: Session = Depends(get_db)):
    contenido = excel_service.exportar_empleados(db)
    fname = f"empleados_{date.today().isoformat()}.xlsx"
    return Response(
        content=contenido,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/importar", response_class=HTMLResponse, name="empleados_importar_form")
def importar_empleados_form(request: Request, db: Session = Depends(get_db)):
    return render(request, db, "empleados/import.html", resultado=None)


@router.post("/importar", response_class=HTMLResponse, name="empleados_importar")
async def importar_empleados(
    request: Request,
    db: Session = Depends(get_db),
    archivo: UploadFile = File(...),
):
    contenido = await archivo.read()
    resultado = excel_service.importar_empleados(db, contenido)
    return render(request, db, "empleados/import.html", resultado=resultado)
