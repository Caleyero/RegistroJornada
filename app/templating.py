"""Templating Jinja2 centralizado.

Expone:
    - `templates`: la única instancia de `Jinja2Templates` de la app.
    - `render(request, db, name, **ctx)`: helper que renderiza un template
      inyectando automáticamente `current_user` y `request` en el contexto.

Usar siempre `render(...)` en lugar de `templates.TemplateResponse(...)`
para que el navbar y la lógica condicional por rol funcionen sin
duplicar la carga del usuario en cada endpoint.
"""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session


TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def render(request: Request, db: Session | None, name: str, **context: Any):
    """Renderiza un template inyectando `current_user` automáticamente.

    Si el endpoint no tiene sesión DB (caso del login), pasar `db=None`.
    """
    if "current_user" not in context:
        if db is not None:
            from app.auth.dependencies import get_current_user
            context["current_user"] = get_current_user(request, db)
        else:
            context["current_user"] = None
    context.setdefault("request", request)
    return templates.TemplateResponse(name, context)
