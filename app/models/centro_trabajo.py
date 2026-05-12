"""Modelo Centro de Trabajo."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class CentroTrabajo(Base):
    __tablename__ = "centros_trabajo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    nombre = Column(String(200), nullable=False)
    direccion = Column(Text)
    ciudad = Column(String(100))
    provincia = Column(String(100))
    codigo_postal = Column(String(5))
    codigo_centro = Column(String(20))
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    empresa = relationship("Empresa", back_populates="centros")
    empleados = relationship("Empleado", back_populates="centro_trabajo")

    def __repr__(self) -> str:
        return f"<CentroTrabajo {self.nombre}>"
