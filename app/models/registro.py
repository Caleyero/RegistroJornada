"""Modelo Registro mensual generado.

Guarda los parámetros usados para generar el PDF (no el PDF en sí).
Permite regenerar exactamente el mismo PDF más adelante o duplicar el
mes anterior para reusar configuración.
"""

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Registro(Base):
    __tablename__ = "registros"
    __table_args__ = (
        UniqueConstraint("empleado_id", "anio", "mes", name="uq_registro_emp_mes"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    anio = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)

    # Horario tipo
    inicio_jornada = Column(String(5), nullable=False)  # "HH:MM"
    inicio_pausa = Column(String(5), nullable=False)
    fin_pausa = Column(String(5), nullable=False)
    fin_jornada = Column(String(5), nullable=False)

    # JSON: [0,1,2,3,4]  -> lun..vie
    dias_laborables = Column(JSON, nullable=False, default=list)
    # JSON: {"2026-04-02": "Jueves Santo", ...}
    festivos = Column(JSON, nullable=False, default=dict)
    # JSON: ["2026-08-01", ...]
    vacaciones = Column(JSON, nullable=False, default=list)
    # JSON: {"2026-05-22": "Cita médica", ...}
    ausencias = Column(JSON, nullable=False, default=dict)
    # JSON: {"2026-05-12": {"inicio_jornada":"09:00", "inicio_pausa":"13:00",
    #                       "fin_pausa":"14:00", "fin_jornada":"17:00"}, ...}
    # Sólo aplica a días laborables que NO sean festivo/vacación/ausencia.
    overrides_horario = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    empleado = relationship("Empleado", back_populates="registros")

    def __repr__(self) -> str:
        return f"<Registro emp={self.empleado_id} {self.anio}-{self.mes:02d}>"
