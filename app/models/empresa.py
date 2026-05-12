"""Modelo Empresa."""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class Empresa(Base):
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    cif = Column(String(9), nullable=False, unique=True)
    direccion = Column(Text)
    codigo_cuenta_cotizacion = Column(String(15))
    activa = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    centros = relationship(
        "CentroTrabajo", back_populates="empresa", cascade="all, delete-orphan",
    )
    empleados = relationship(
        "Empleado", back_populates="empresa", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Empresa {self.cif} - {self.nombre}>"
