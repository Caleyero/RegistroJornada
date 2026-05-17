"""Modelo PeriodoNoApto.

Rango de fechas en el que un centro desaconseja (o veta) las vacaciones:
campañas, rebajas, inventario, Navidad... El planificador avisa cuando
unas vacaciones solapan con uno de estos periodos.
"""

from sqlalchemy import (
    CheckConstraint, Column, Date, ForeignKey, Integer, String,
)
from sqlalchemy.orm import relationship

from app.database import Base


class PeriodoNoApto(Base):
    __tablename__ = "periodo_no_apto"
    __table_args__ = (
        CheckConstraint(
            "fecha_fin >= fecha_inicio", name="ck_periodo_no_apto_fechas",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    centro_id = Column(
        Integer, ForeignKey("centros_trabajo.id"), nullable=False, index=True,
    )
    nombre = Column(String(100), nullable=False)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=False)

    centro = relationship("CentroTrabajo", back_populates="periodos_no_aptos")

    def __repr__(self) -> str:
        return f"<PeriodoNoApto centro={self.centro_id} {self.nombre}>"
