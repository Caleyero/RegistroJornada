"""Modelo CentroHorarioApertura.

Horario de apertura de un centro para cada día de la semana. Una fila por
(centro, día). Sirve para validar que un turno planificado cae dentro del
horario en que la tienda está abierta.
"""

from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class CentroHorarioApertura(Base):
    __tablename__ = "centro_horario_apertura"
    __table_args__ = (
        UniqueConstraint("centro_id", "dia_semana", name="uq_horario_centro_dow"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    centro_id = Column(
        Integer, ForeignKey("centros_trabajo.id"), nullable=False, index=True,
    )
    # 0..6 (lunes..domingo), mismo criterio que dias_laborables.
    dia_semana = Column(Integer, nullable=False)
    cerrado = Column(Boolean, nullable=False, default=False)
    apertura = Column(String(5))  # "HH:MM" — None si el centro cierra ese día
    cierre = Column(String(5))
    # Pausa de mediodía (horario partido). None en jornada continua.
    inicio_pausa = Column(String(5))  # hora en que cierra a mediodía
    fin_pausa = Column(String(5))     # hora en que reabre por la tarde

    @property
    def es_partido(self) -> bool:
        return bool(self.inicio_pausa and self.fin_pausa)

    centro = relationship("CentroTrabajo", back_populates="horarios_apertura")

    def __repr__(self) -> str:
        return f"<CentroHorarioApertura centro={self.centro_id} dow={self.dia_semana}>"
