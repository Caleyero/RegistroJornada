"""Panel admin: gestión de usuarios.

Acceso restringido a administradores. Cada Usuario representa una identidad
que puede entrar al sistema por DNI; opcionalmente está vinculado a un
Empleado (caso normal: el usuario es el propio empleado).

Reglas:
    - El DNI es único.
    - Un empleado puede tener como máximo un usuario.
    - Un admin no puede auto-desactivarse, auto-eliminarse ni quitarse el rol
      si es el último admin activo.
"""

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.dependencies import get_db
from app.models import Empleado, Usuario
from app.models.usuario import ROL_ADMIN, ROL_EMPLEADO, ROLES_VALIDOS
from app.services import excel_service
from app.templating import render


router = APIRouter(
    prefix="/admin/usuarios",
    tags=["admin-usuarios"],
    dependencies=[Depends(require_admin)],
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _empleados_disponibles(db: Session, usuario_actual_id: int | None = None):
    """Empleados sin usuario asignado (más el del usuario que se edita).

    Permite editar un usuario manteniendo la opción "su empleado actual" en
    el select, sin que el filtro de "sin usuario" lo excluya.
    """
    query = db.query(Empleado).outerjoin(Usuario)
    if usuario_actual_id is None:
        query = query.filter(Usuario.id.is_(None))
    else:
        query = query.filter(
            (Usuario.id.is_(None)) | (Usuario.id == usuario_actual_id)
        )
    return query.order_by(Empleado.apellidos, Empleado.nombre).all()


def _ultimo_admin_activo(db: Session, excluir_id: int) -> bool:
    """True si excluir el usuario `excluir_id` dejaría 0 admins activos."""
    otros = (
        db.query(Usuario)
        .filter(
            Usuario.es_admin == True,  # noqa: E712
            Usuario.activo == True,  # noqa: E712
            Usuario.id != excluir_id,
        )
        .count()
    )
    return otros == 0


@router.get("", response_class=HTMLResponse, name="admin_usuarios_list")
def list_usuarios(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
):
    usuarios = (
        db.query(Usuario)
        .outerjoin(Empleado, Empleado.id == Usuario.empleado_id)
        .order_by(Usuario.es_admin.desc(), Usuario.dni)
        .all()
    )
    return render(
        request, db, "admin/usuarios/list.html",
        current_user=current, usuarios=usuarios,
    )


@router.get("/nuevo", response_class=HTMLResponse, name="admin_usuarios_new")
def new_usuario_form(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
):
    empleados = _empleados_disponibles(db)
    return render(
        request, db, "admin/usuarios/form.html",
        current_user=current, usuario=None, empleados=empleados, error=None,
    )


@router.post("/nuevo", name="admin_usuarios_create")
def create_usuario(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
    dni: str = Form(...),
    empleado_id: str = Form(""),
    rol: str = Form(ROL_EMPLEADO),
    activo: bool = Form(False),
):
    if rol not in ROLES_VALIDOS:
        rol = ROL_EMPLEADO
    dni_norm = dni.strip().upper()
    if not dni_norm:
        empleados = _empleados_disponibles(db)
        return render(
            request, db, "admin/usuarios/form.html",
            current_user=current, usuario=None, empleados=empleados,
            error="El DNI es obligatorio.",
        )

    if db.query(Usuario).filter(Usuario.dni == dni_norm).first():
        empleados = _empleados_disponibles(db)
        return render(
            request, db, "admin/usuarios/form.html",
            current_user=current, usuario=None, empleados=empleados,
            error=f"Ya existe un usuario con DNI {dni_norm}.",
        )

    emp_id: int | None = int(empleado_id) if empleado_id.strip() else None
    if emp_id is not None:
        empleado = db.get(Empleado, emp_id)
        if empleado is None:
            raise HTTPException(status_code=400, detail="Empleado inexistente.")
        if empleado.usuario is not None:
            empleados = _empleados_disponibles(db)
            return render(
                request, db, "admin/usuarios/form.html",
                current_user=current, usuario=None, empleados=empleados,
                error="Ese empleado ya tiene un usuario asignado.",
            )

    usuario = Usuario(
        dni=dni_norm,
        empleado_id=emp_id,
        rol=rol,
        activo=activo,
    )
    db.add(usuario)
    db.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.get("/{usuario_id}/editar", response_class=HTMLResponse, name="admin_usuarios_edit")
def edit_usuario_form(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    empleados = _empleados_disponibles(db, usuario_actual_id=usuario.id)
    return render(
        request, db, "admin/usuarios/form.html",
        current_user=current, usuario=usuario, empleados=empleados, error=None,
    )


@router.post("/{usuario_id}/editar", name="admin_usuarios_update")
def update_usuario(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
    dni: str = Form(...),
    empleado_id: str = Form(""),
    rol: str = Form(ROL_EMPLEADO),
    activo: bool = Form(False),
):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if rol not in ROLES_VALIDOS:
        rol = ROL_EMPLEADO

    dni_norm = dni.strip().upper()
    if not dni_norm:
        empleados = _empleados_disponibles(db, usuario_actual_id=usuario.id)
        return render(
            request, db, "admin/usuarios/form.html",
            current_user=current, usuario=usuario, empleados=empleados,
            error="El DNI es obligatorio.",
        )

    if dni_norm != usuario.dni:
        choque = db.query(Usuario).filter(Usuario.dni == dni_norm).first()
        if choque is not None:
            empleados = _empleados_disponibles(db, usuario_actual_id=usuario.id)
            return render(
                request, db, "admin/usuarios/form.html",
                current_user=current, usuario=usuario, empleados=empleados,
                error=f"Ya existe otro usuario con DNI {dni_norm}.",
            )

    emp_id: int | None = int(empleado_id) if empleado_id.strip() else None
    if emp_id is not None and emp_id != usuario.empleado_id:
        empleado = db.get(Empleado, emp_id)
        if empleado is None:
            raise HTTPException(status_code=400, detail="Empleado inexistente.")
        if empleado.usuario is not None and empleado.usuario.id != usuario.id:
            empleados = _empleados_disponibles(db, usuario_actual_id=usuario.id)
            return render(
                request, db, "admin/usuarios/form.html",
                current_user=current, usuario=usuario, empleados=empleados,
                error="Ese empleado ya tiene un usuario asignado.",
            )

    # Validaciones de auto-protección
    es_propio = usuario.id == current.id
    if es_propio and not activo:
        empleados = _empleados_disponibles(db, usuario_actual_id=usuario.id)
        return render(
            request, db, "admin/usuarios/form.html",
            current_user=current, usuario=usuario, empleados=empleados,
            error="No puedes desactivar tu propio usuario.",
        )
    if es_propio and rol != ROL_ADMIN:
        empleados = _empleados_disponibles(db, usuario_actual_id=usuario.id)
        return render(
            request, db, "admin/usuarios/form.html",
            current_user=current, usuario=usuario, empleados=empleados,
            error="No puedes retirarte a ti mismo el rol de administrador.",
        )

    # No degradar/desactivar al último admin activo
    pierde_admin = usuario.es_admin and rol != ROL_ADMIN
    se_desactiva = usuario.activo and not activo
    if (pierde_admin or se_desactiva) and usuario.es_admin and usuario.activo:
        if _ultimo_admin_activo(db, excluir_id=usuario.id):
            empleados = _empleados_disponibles(db, usuario_actual_id=usuario.id)
            return render(
                request, db, "admin/usuarios/form.html",
                current_user=current, usuario=usuario, empleados=empleados,
                error="No se puede dejar el sistema sin administrador activo.",
            )

    usuario.dni = dni_norm
    usuario.empleado_id = emp_id
    usuario.rol = rol
    usuario.activo = activo
    db.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/{usuario_id}/toggle-activo", name="admin_usuarios_toggle")
def toggle_activo(
    usuario_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if usuario.id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propio usuario.",
        )
    if usuario.activo and usuario.es_admin and _ultimo_admin_activo(db, excluir_id=usuario.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede dejar el sistema sin administrador activo.",
        )
    usuario.activo = not usuario.activo
    db.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.post("/{usuario_id}/eliminar", name="admin_usuarios_delete")
def delete_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
):
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if usuario.id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes eliminar tu propio usuario.",
        )
    if usuario.es_admin and usuario.activo and _ultimo_admin_activo(db, excluir_id=usuario.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar al último administrador activo.",
        )
    db.delete(usuario)
    db.commit()
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.get("/exportar", name="admin_usuarios_exportar")
def exportar_usuarios(db: Session = Depends(get_db)):
    contenido = excel_service.exportar_usuarios(db)
    fname = f"usuarios_{date.today().isoformat()}.xlsx"
    return Response(
        content=contenido,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/importar", response_class=HTMLResponse, name="admin_usuarios_importar_form")
def importar_usuarios_form(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
):
    return render(
        request, db, "admin/usuarios/import.html",
        current_user=current, resultado=None,
    )


@router.post("/importar", response_class=HTMLResponse, name="admin_usuarios_importar")
async def importar_usuarios(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_admin),
    archivo: UploadFile = File(...),
):
    contenido = await archivo.read()
    resultado = excel_service.importar_usuarios(db, contenido)
    return render(
        request, db, "admin/usuarios/import.html",
        current_user=current, resultado=resultado,
    )
