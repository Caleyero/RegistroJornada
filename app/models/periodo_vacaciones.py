"""Modelo PeriodoVacaciones.

Tramo de fechas en que un empleado no está disponible: vacaciones, baja o
permiso. Lo gestiona RRHH directamente. El planificador lo usa para
detectar conflictos (asignar turno a alguien de vacaciones) y para
calcular el cupo anual consumido.
"""

from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


TIPO_VACACIONES = "vacaciones"
TIPO_BAJA = "baja"
TIPO_PERMISO = "permiso"
TIPOS_VALIDOS = {TIPO_VACACIONES, TIPO_BAJA, TIPO_PERMISO}

TIPO_ETIQUETAS = {
    TIPO_VACACIONES: "Vacaciones",
    TIPO_BAJA: "Baja",
    TIPO_PERMISO: "Permiso",
}


class PeriodoVacaciones(Base):
    __tablename__ = "periodo_vacaciones"
    __table_args__ = (
        CheckConstraint(
            "fecha_fin >= fecha_inicio", name="ck_periodo_vac_fechas",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(
        Integer, ForeignKey("empleados.id"), nullable=False, index=True,
    )
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=False)
    tipo = Column(String(12), nullable=False, default=TIPO_VACACIONES)
    observaciones = Column(String(200))

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    empleado = relationship("Empleado", back_populates="periodos_vacaciones")

    @property
    def dias(self) -> int:
        """Número de días naturales del periodo (ambos extremos incluidos)."""
        return (self.fecha_fin - self.fecha_inicio).days + 1

    def cubre(self, fecha) -> bool:
        return self.fecha_inicio <= fecha <= self.fecha_fin

    def __repr__(self) -> str:
        return (
            f"<PeriodoVacaciones emp={self.empleado_id} {self.tipo} "
            f"{self.fecha_inicio}..{self.fecha_fin}>"
        )
