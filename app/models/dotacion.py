"""Modelo DotacionCentro.

Dotación de personal de un centro: cuántas personas se necesitan como
mínimo y como máximo para cada combinación de día de la semana y turno.
Es la referencia con la que el planificador calcula el semáforo de
cobertura (faltan / cubierto / exceso).
"""

from sqlalchemy import (
    CheckConstraint, Column, ForeignKey, Integer, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class DotacionCentro(Base):
    __tablename__ = "dotacion_centro"
    __table_args__ = (
        UniqueConstraint(
            "centro_id", "plantilla_turno_id", "dia_semana", name="uq_dotacion",
        ),
        CheckConstraint(
            "minimo >= 0 AND maximo >= minimo", name="ck_dotacion_rango",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    centro_id = Column(
        Integer, ForeignKey("centros_trabajo.id"), nullable=False, index=True,
    )
    plantilla_turno_id = Column(
        Integer, ForeignKey("plantilla_turno.id"), nullable=False, index=True,
    )
    dia_semana = Column(Integer, nullable=False)  # 0..6 (lun..dom)
    minimo = Column(Integer, nullable=False, default=1)
    maximo = Column(Integer, nullable=False, default=1)

    centro = relationship("CentroTrabajo", back_populates="dotaciones")
    plantilla_turno = relationship("PlantillaTurno", back_populates="dotaciones")

    def __repr__(self) -> str:
        return (
            f"<DotacionCentro centro={self.centro_id} "
            f"turno={self.plantilla_turno_id} dow={self.dia_semana} "
            f"{self.minimo}-{self.maximo}>"
        )
