"""Modelo RegistroDiario.

Una fila por (empleado, fecha) que recoge la jornada efectivamente trabajada
o el motivo por el que ese día no se trabajó. Es la fuente de verdad del
art. 34.9 del Estatuto de los Trabajadores (registro diario).

El `Registro` mensual sigue existiendo como soporte documental (PDF firmado);
al cerrarse el mes, los días pasan a `cerrado=True` y se vuelven inmutables
salvo reapertura del admin.
"""

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


# Tipos válidos para la columna `tipo`. Mantener en sync con el wizard de PDF
# y con el helper diario_service.dias_a_eventos.
TIPO_TRABAJADO = "trabajado"
TIPO_FESTIVO = "festivo"
TIPO_VACACIONES = "vacaciones"
TIPO_AUSENCIA = "ausencia"
TIPO_DESCANSO = "descanso"

TIPOS_VALIDOS = {
    TIPO_TRABAJADO, TIPO_FESTIVO, TIPO_VACACIONES, TIPO_AUSENCIA, TIPO_DESCANSO,
}

# Fuente de la fila — útil para distinguir prefills automáticos de
# confirmaciones manuales o de regularizaciones desde el wizard mensual.
FUENTE_AUTO = "auto"
FUENTE_MANUAL = "manual"
FUENTE_WIZARD = "wizard"


class RegistroDiario(Base):
    __tablename__ = "registros_diarios"
    __table_args__ = (
        UniqueConstraint("empleado_id", "fecha", name="uq_regdia_emp_fecha"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(
        Integer, ForeignKey("empleados.id"), nullable=False, index=True,
    )
    fecha = Column(Date, nullable=False, index=True)

    tipo = Column(String(20), nullable=False, default=TIPO_TRABAJADO)

    inicio_jornada = Column(String(5))  # "HH:MM" — solo si tipo == trabajado
    inicio_pausa = Column(String(5))
    fin_pausa = Column(String(5))
    fin_jornada = Column(String(5))

    observaciones = Column(String(200))
    fuente = Column(String(10), nullable=False, default=FUENTE_AUTO)
    cerrado = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    empleado = relationship("Empleado", back_populates="registros_diarios")

    def __repr__(self) -> str:
        return f"<RegistroDiario emp={self.empleado_id} {self.fecha} {self.tipo}>"
