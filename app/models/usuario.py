"""Modelo Usuario.

Representa una identidad capaz de acceder al sistema. El login se hace
únicamente por DNI (sin contraseña), por lo que esta tabla solo guarda
el DNI, el rol y, si procede, el empleado asociado.

Un Usuario puede estar vinculado a un Empleado (caso normal) o no
estarlo (caso del administrador del sistema, que puede no trabajar para
ninguna de las empresas registradas).
"""

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dni = Column(String(9), nullable=False, unique=True, index=True)
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

    @property
    def nombre_visible(self) -> str:
        if self.empleado is not None:
            return self.empleado.nombre_completo
        if self.es_admin:
            return "Administrador"
        return self.dni

    def __repr__(self) -> str:
        rol = "admin" if self.es_admin else "usuario"
        return f"<Usuario {self.dni} ({rol})>"
