"""Rutas de autenticación: /login y /logout.

Login sin contraseña: el usuario teclea su DNI; si existe en la tabla
`usuarios` y está activo, se guarda su id en `request.session`. No hay
recovery, no hay registro público — la gestión de altas es manual y la
hace el admin desde /admin/usuarios.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Usuario
from app.templating import render


router = APIRouter(tags=["auth"])


@router.get("/login")
def login_form(request: Request, error: str | None = None) -> Response:
    return render(
        request, None, "auth/login.html",
        error=error, current_user=None,
    )


@router.post("/login")
def login_submit(
    request: Request,
    dni: str = Form(...),
    db: Session = Depends(get_db),
) -> Response:
    dni_norm = dni.strip().upper()
    if not dni_norm:
        return render(
            request, None, "auth/login.html",
            error="Introduce tu DNI.", current_user=None, dni=dni,
        )

    usuario = db.query(Usuario).filter(Usuario.dni == dni_norm).one_or_none()
    if usuario is None:
        return render(
            request, None, "auth/login.html",
            error="DNI no reconocido. Pídele al administrador que te dé de alta.",
            current_user=None, dni=dni_norm,
        )
    if not usuario.activo:
        return render(
            request, None, "auth/login.html",
            error="Tu usuario está desactivado. Contacta con el administrador.",
            current_user=None, dni=dni_norm,
        )

    request.session["user_id"] = usuario.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
