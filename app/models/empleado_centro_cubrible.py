"""Tabla puente Empleado ↔ CentroTrabajo: centros cubribles.

Relación muchos-a-muchos que responde a la vez a dos preguntas que son la
misma vista desde dos lados:
    - ¿A qué centros se puede desplazar este empleado?
    - ¿Qué empleados pueden cubrir las necesidades de este centro?

El centro de trabajo propio del empleado NO se almacena aquí: se considera
cubrible de forma implícita (ver `Empleado.centros_cubribles_efectivos`).
"""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.database import Base


empleado_centro_cubrible = Table(
    "empleado_centro_cubrible",
    Base.metadata,
    Column(
        "empleado_id", Integer,
        ForeignKey("empleados.id", ondelete="CASCADE"), primary_key=True,
    ),
    Column(
        "centro_id", Integer,
        ForeignKey("centros_trabajo.id", ondelete="CASCADE"), primary_key=True,
    ),
)
