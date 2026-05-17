"""Modelo Usuario.

Representa una identidad capaz de acceder al sistema. El login se hace
únicamente por DNI (sin contraseña), por lo que esta tabla solo guarda
el DNI, el rol y, si procede, el empleado asociado.

Un Usuario puede estar vinculado a un Empleado (caso normal) o no
estarlo (caso del administrador del sistema, que puede no trabajar para
ninguna de las empresas registradas).

Roles
-----
La columna `rol` es la fuente de verdad del nivel de acceso:
    - `admin`    — acceso total (configuración, usuarios, planificación...).
    - `rrhh`     — planificación de turnos y vacaciones de todos los centros,
                   sin acceso a la configuración de empresas/usuarios.
    - `empleado` — solo su propio registro diario.

`es_admin` se conserva como columna espejo (sincronizada vía @validates)
para no romper el código y las consultas existentes que aún la usan.
"""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, func,
)
from sqlalchemy.orm import relationship, validates

from app.database import Base


# Valores válidos de la columna `rol`.
ROL_ADMIN = "admin"
ROL_RRHH = "rrhh"
ROL_EMPLEADO = "empleado"
ROLES_VALIDOS = {ROL_ADMIN, ROL_RRHH, ROL_EMPLEADO}

# Etiqueta legible por rol — útil en formularios y plantillas.
ROL_ETIQUETAS = {
    ROL_ADMIN: "Administrador",
    ROL_RRHH: "RRHH",
    ROL_EMPLEADO: "Empleado",
}


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dni = Column(String(9), nullable=False, unique=True, index=True)
    # Fuente de verdad del nivel de acceso.
    rol = Column(String(10), nullable=False, default=ROL_EMPLEADO)
    # Columna espejo de `rol == 'admin'`: la mantiene sincronizada el
    # validador de abajo. Se conserva por compatibilidad con el código y
    # las consultas existentes.
    es_admin = Column(Boolean, default=False, nullable=False)
    # ondelete=SET NULL: si se elimina el empleado, el usuario sobrevive
    # pero queda huérfano (sin acceso a registros). Requiere
    # PRAGMA foreign_keys=ON en SQLite (configurado en app/database.py).
    empleado_id = Column(
        Integer,
        ForeignKey("empleados.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    empleado = relationship("Empleado", back_populates="usuario", uselist=False)

    @validates("rol")
    def _sync_es_admin(self, key: str, value: str) -> str:
        """Mantiene `es_admin` como espejo de `rol` en cada asignación."""
        self.es_admin = value == ROL_ADMIN
        return value

    @property
    def es_rrhh(self) -> bool:
        """True si el usuario tiene rol RRHH (no incluye al admin)."""
        return self.rol == ROL_RRHH

    @property
    def puede_planificar(self) -> bool:
        """True si puede acceder a planificación y vacaciones (admin o RRHH)."""
        return self.rol in (ROL_ADMIN, ROL_RRHH)

    @property
    def nombre_visible(self) -> str:
        if self.empleado is not None:
            return self.empleado.nombre_completo
        if self.rol == ROL_ADMIN:
            return "Administrador"
        if self.rol == ROL_RRHH:
            return "RRHH"
        return self.dni

    def __repr__(self) -> str:
        return f"<Usuario {self.dni} ({self.rol})>"
