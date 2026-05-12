"""Crea las tablas y, opcionalmente, datos demo.

Uso:
    python -m scripts.init_db          # solo crea tablas
    python -m scripts.init_db --demo   # añade una empresa+centro+empleado de prueba
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base, SessionLocal, engine
from app.models import CentroTrabajo, Empleado, Empresa  # noqa: F401


def main(con_demo: bool) -> None:
    print("Creando tablas SQLite...")
    Base.metadata.create_all(bind=engine)
    print("OK")

    if not con_demo:
        return

    db = SessionLocal()
    try:
        if db.query(Empresa).count() > 0:
            print("Ya hay datos en la BBDD — no se inserta demo.")
            return

        emp = Empresa(
            nombre="Empresa Demo SL",
            cif="B12345678",
            direccion="Calle Mayor 1, 33001 Oviedo",
            codigo_cuenta_cotizacion="33012345678",
        )
        db.add(emp); db.flush()

        centro = CentroTrabajo(
            empresa_id=emp.id,
            nombre="Oficina Central",
            direccion="Calle Mayor 1",
            ciudad="Oviedo",
            provincia="Asturias",
            codigo_postal="33001",
            codigo_centro="OFC-001",
        )
        db.add(centro); db.flush()

        trabajador = Empleado(
            empresa_id=emp.id,
            centro_trabajo_id=centro.id,
            nombre="Ana",
            apellidos="García López",
            nif="12345678A",
            numero_afiliacion_ss="331234567890",
            categoria_profesional="Administrativa",
            tipo_contrato="indefinido",
            horas_semanales=40,
            fecha_alta=date(2024, 1, 15),
            email="ana.garcia@demo.es",
        )
        db.add(trabajador)
        db.commit()
        print("Demo creada: 1 empresa, 1 centro, 1 empleado.")
    finally:
        db.close()


if __name__ == "__main__":
    main(con_demo="--demo" in sys.argv)
