"""Modelo Empleado."""

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, ForeignKey,
    Integer, Numeric, String, func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Empleado(Base):
    __tablename__ = "empleados"

    id = Column(Integer, primary_key=True, autoincrement=True)
    empresa_id = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    centro_trabajo_id = Column(Integer, ForeignKey("centros_trabajo.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    apellidos = Column(String(200), nullable=False)
    nif = Column(String(9), nullable=False, unique=True)
    numero_afiliacion_ss = Column(String(15))
    categoria_profesional = Column(String(100))
    tipo_contrato = Column(String(50))
    horas_semanales = Column(Numeric(4, 2), default=40.00)
    fecha_alta = Column(Date)
    fecha_baja = Column(Date)
    activo = Column(Boolean, default=True, nullable=False)
    email = Column(String(200))
    telefono = Column(String(20))

    # Horario habitual (jornada partida): si esta a None, el wizard usa
    # los defaults globales. Permite jornada continua dejando vacios
    # `inicio_pausa` y `fin_pausa`.
    inicio_jornada = Column(String(5))  # "HH:MM"
    inicio_pausa = Column(String(5))
    fin_pausa = Column(String(5))
    fin_jornada = Column(String(5))
    # Lista [0..6] (lun..dom). Si None, el wizard cae al default L-V.
    dias_laborables_habituales = Column(JSON)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    empresa = relationship("Empresa", back_populates="empleados")
    centro_trabajo = relationship("CentroTrabajo", back_populates="empleados")
    registros = relationship(
        "Registro", back_populates="empleado", cascade="all, delete-orphan",
    )
    usuario = relationship("Usuario", back_populates="empleado", uselist=False)

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellidos}"

    def __repr__(self) -> str:
        return f"<Empleado {self.nif} - {self.nombre_completo}>"
