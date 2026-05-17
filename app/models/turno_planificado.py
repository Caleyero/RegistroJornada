"""Modelo TurnoPlanificado.

Asignación de un empleado a un turno, en un centro y una fecha concretos.
Es la capa de PREVISIÓN: dice qué *debería* ocurrir. No sustituye al
`RegistroDiario` (lo realmente trabajado, art. 34.9 ET); al publicarse el
plan puede volcarse como prefill de aquel.

El `centro_id` puede diferir del centro propio del empleado: ahí es donde
se modela el desplazamiento para cubrir a otra tienda.
"""

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


ESTADO_BORRADOR = "borrador"
ESTADO_PUBLICADO = "publicado"
ESTADOS_VALIDOS = {ESTADO_BORRADOR, ESTADO_PUBLICADO}


class TurnoPlanificado(Base):
    __tablename__ = "turno_planificado"
    __table_args__ = (
        UniqueConstraint("empleado_id", "fecha", name="uq_turno_emp_fecha"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False, index=True)
    empleado_id = Column(
        Integer, ForeignKey("empleados.id"), nullable=False, index=True,
    )
    # Centro donde el empleado cubre ese día (puede no ser el suyo propio).
    centro_id = Column(
        Integer, ForeignKey("centros_trabajo.id"), nullable=False, index=True,
    )
    # Plantilla de la que sale el turno; NULL si fue un turno ad-hoc.
    plantilla_turno_id = Column(
        Integer, ForeignKey("plantilla_turno.id"), nullable=True,
    )
    # Horario materializado (copia de la plantilla al asignar; editable).
    hora_inicio = Column(String(5), nullable=False)
    hora_fin = Column(String(5), nullable=False)
    inicio_pausa = Column(String(5))
    fin_pausa = Column(String(5))

    estado = Column(String(12), nullable=False, default=ESTADO_BORRADOR)
    # True cuando el turno ya se ha volcado al RegistroDiario.
    volcado_diario = Column(Boolean, nullable=False, default=False)
    observaciones = Column(String(200))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    empleado = relationship("Empleado", back_populates="turnos_planificados")
    centro = relationship("CentroTrabajo", back_populates="turnos_planificados")
    plantilla_turno = relationship("PlantillaTurno")

    def __repr__(self) -> str:
        return (
            f"<TurnoPlanificado emp={self.empleado_id} {self.fecha} "
            f"centro={self.centro_id}>"
        )
