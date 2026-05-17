"""Modelo PlantillaTurno.

Plantilla de turno de un centro (p. ej. "Mañana", "Tarde", "Partido").
Define el horario reutilizable que luego se asigna a empleados en la
planificación. Cada centro tiene sus propias plantillas porque los
horarios comerciales varían de una tienda a otra.
"""

from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class PlantillaTurno(Base):
    __tablename__ = "plantilla_turno"
    __table_args__ = (
        UniqueConstraint("centro_id", "nombre", name="uq_turno_centro_nombre"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    centro_id = Column(
        Integer, ForeignKey("centros_trabajo.id"), nullable=False, index=True,
    )
    nombre = Column(String(50), nullable=False)
    hora_inicio = Column(String(5), nullable=False)  # "HH:MM"
    hora_fin = Column(String(5), nullable=False)
    inicio_pausa = Column(String(5))  # opcional (turno partido)
    fin_pausa = Column(String(5))
    activo = Column(Boolean, nullable=False, default=True)
    orden = Column(Integer, nullable=False, default=0)

    centro = relationship("CentroTrabajo", back_populates="plantillas_turno")
    dotaciones = relationship(
        "DotacionCentro", back_populates="plantilla_turno",
        cascade="all, delete-orphan",
    )

    @property
    def etiqueta(self) -> str:
        return f"{self.nombre} ({self.hora_inicio}–{self.hora_fin})"

    def __repr__(self) -> str:
        return f"<PlantillaTurno centro={self.centro_id} {self.nombre}>"
