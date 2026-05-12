"""Festivos del Principado de Asturias (nacionales + autonómicos).

No incluye fiestas locales de los concejos. Verificar con el BOPA cada año.
"""


FESTIVOS_ASTURIAS: dict[str, str] = {
    # 2024
    "2024-01-01": "Año Nuevo",
    "2024-01-06": "Reyes",
    "2024-03-28": "Jueves Santo",
    "2024-03-29": "Viernes Santo",
    "2024-05-01": "Día del Trabajo",
    "2024-08-15": "Asunción",
    "2024-09-09": "Día de Asturias (trasl.)",
    "2024-11-01": "Todos los Santos",
    "2024-12-06": "Constitución",
    "2024-12-09": "Inmaculada (trasl.)",
    "2024-12-25": "Navidad",
    # 2025
    "2025-01-01": "Año Nuevo",
    "2025-01-06": "Reyes",
    "2025-04-17": "Jueves Santo",
    "2025-04-18": "Viernes Santo",
    "2025-05-01": "Día del Trabajo",
    "2025-08-15": "Asunción",
    "2025-09-08": "Día de Asturias",
    "2025-11-01": "Todos los Santos",
    "2025-12-06": "Constitución",
    "2025-12-08": "Inmaculada",
    "2025-12-25": "Navidad",
    # 2026 — Resolución del Principado publicada en el BOPA
    "2026-01-01": "Año Nuevo",
    "2026-01-06": "Reyes",
    "2026-04-02": "Jueves Santo",
    "2026-04-03": "Viernes Santo",
    "2026-05-01": "Día del Trabajo",
    "2026-08-15": "Asunción",
    "2026-09-08": "Día de Asturias",
    "2026-10-12": "Fiesta Nacional de España",
    "2026-11-02": "Todos los Santos (trasl.)",
    "2026-12-07": "Constitución (trasl.)",
    "2026-12-08": "Inmaculada",
    "2026-12-25": "Navidad",
    # 2027 (provisional)
    "2027-01-01": "Año Nuevo",
    "2027-01-06": "Reyes",
    "2027-03-25": "Jueves Santo",
    "2027-03-26": "Viernes Santo",
    "2027-09-08": "Día de Asturias",
    "2027-10-12": "Fiesta Nacional de España",
    "2027-11-01": "Todos los Santos",
    "2027-12-06": "Constitución",
    "2027-12-08": "Inmaculada",
    "2027-12-25": "Navidad",
}


def festivos_del_mes(anio: int, mes: int) -> dict[str, str]:
    """Devuelve los festivos del mes pedido: {fecha_iso: descripcion}."""
    prefijo = f"{anio:04d}-{mes:02d}-"
    return {f: d for f, d in FESTIVOS_ASTURIAS.items() if f.startswith(prefijo)}
