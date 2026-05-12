"""Dependencias de autenticación.

El login es solo por DNI (sin contraseña). Tras validar el DNI, el id
del Usuario se guarda en la cookie de sesión firmada con SECRET_KEY.
Estas dependencias leen esa cookie y resuelven el usuario actual.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Usuario


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Usuario | None:
    """Devuelve el Usuario de la sesión o None.

    Si la sesión apunta a un id inexistente o desactivado, se limpia la
    sesión y se devuelve None (el usuario verá /login al siguiente paso).
    Esta función NO lanza excepciones — sirve para endpoints que pueden
    ser públicos o autenticados según la situación.
    """
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    usuario = db.get(Usuario, user_id)
    if usuario is None or not usuario.activo:
        request.session.clear()
        return None
    # Cache en request.state para que otras dependencias del mismo request
    # no vuelvan a consultar la BD.
    request.state.current_user = usuario
    return usuario


def require_login(
    request: Request, db: Session = Depends(get_db),
) -> Usuario:
    """Exige sesión válida. Lanza 401 si no la hay (se redirige en main.py)."""
    cached = getattr(request.state, "current_user", None)
    if cached is not None:
        return cached
    usuario = get_current_user(request, db)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return usuario


def require_admin(current: Usuario = Depends(require_login)) -> Usuario:
    """Exige sesión válida con rol admin. Lanza 403 si el usuario no es admin."""
    if not current.es_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere rol de administrador.",
        )
    return current
