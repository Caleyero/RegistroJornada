"""Validación de vacaciones, bajas y permisos.

RRHH gestiona los periodos directamente; este servicio comprueba antes de
guardar: solapamientos, cupo anual, periodos no aptos del centro e
impacto en la dotación mínima.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import DotacionCentro, Empleado, PeriodoNoApto, PeriodoVacaciones
from app.models.periodo_vacaciones import TIPO_VACACIONES
from app.services.conflictos_service import (
    Conflicto, SEV_ADVERTENCIA, SEV_BLOQUEANTE,
)


def _dias_en_anio(fecha_inicio: date, fecha_fin: date, anio: int) -> int:
    """Número de días del rango (incl.) que caen dentro de `anio`."""
    ini = max(fecha_inicio, date(anio, 1, 1))
    fin = min(fecha_fin, date(anio, 12, 31))
    if fin < ini:
        return 0
    return (fin - ini).days + 1


def dias_vacaciones_consumidos(
    db: Session, empleado_id: int, anio: int, excluir_id: int | None = None,
) -> int:
    """Días de vacaciones (no bajas ni permisos) del empleado en ese año."""
    q = db.query(PeriodoVacaciones).filter(
        PeriodoVacaciones.empleado_id == empleado_id,
        PeriodoVacaciones.tipo == TIPO_VACACIONES,
    )
    if excluir_id is not None:
        q = q.filter(PeriodoVacaciones.id != excluir_id)
    return sum(_dias_en_anio(p.fecha_inicio, p.fecha_fin, anio) for p in q.all())


def periodos_solapados(
    db: Session, empleado_id: int, fecha_inicio: date, fecha_fin: date,
    excluir_id: int | None = None,
) -> list[PeriodoVacaciones]:
    """Periodos del empleado que solapan con [fecha_inicio, fecha_fin]."""
    q = db.query(PeriodoVacaciones).filter(
        PeriodoVacaciones.empleado_id == empleado_id,
        PeriodoVacaciones.fecha_inicio <= fecha_fin,
        PeriodoVacaciones.fecha_fin >= fecha_inicio,
    )
    if excluir_id is not None:
        q = q.filter(PeriodoVacaciones.id != excluir_id)
    return q.all()


def _dias_bajo_minimo(
    db: Session, empleado: Empleado, fecha_inicio: date, fecha_fin: date,
) -> int:
    """Cuenta los días del rango que dejarían el centro bajo mínimos.

    Heurística: compara la plantilla activa del centro, descontando a los
    ausentes ese día, con la suma de dotaciones mínimas del día de la
    semana. No considera cubridores externos — por eso es solo un aviso.
    """
    centro_id = empleado.centro_trabajo_id
    if centro_id is None:
        return 0

    n_plantilla = (
        db.query(Empleado)
        .filter(Empleado.centro_trabajo_id == centro_id, Empleado.activo.is_(True))
        .count()
    )
    min_por_dow: dict[int, int] = {}
    for d in (
        db.query(DotacionCentro)
        .filter(DotacionCentro.centro_id == centro_id)
        .all()
    ):
        min_por_dow[d.dia_semana] = min_por_dow.get(d.dia_semana, 0) + d.minimo

    otros = (
        db.query(PeriodoVacaciones)
        .join(Empleado, Empleado.id == PeriodoVacaciones.empleado_id)
        .filter(
            Empleado.centro_trabajo_id == centro_id,
            PeriodoVacaciones.empleado_id != empleado.id,
            PeriodoVacaciones.fecha_inicio <= fecha_fin,
            PeriodoVacaciones.fecha_fin >= fecha_inicio,
        )
        .all()
    )

    dias_riesgo = 0
    dia = fecha_inicio
    while dia <= fecha_fin:
        minimo = min_por_dow.get(dia.weekday(), 0)
        if minimo > 0:
            ausentes = 1 + sum(
                1 for p in otros if p.fecha_inicio <= dia <= p.fecha_fin
            )
            if n_plantilla - ausentes < minimo:
                dias_riesgo += 1
        dia += timedelta(days=1)
    return dias_riesgo


def validar_periodo(
    db: Session,
    empleado: Empleado,
    fecha_inicio: date,
    fecha_fin: date,
    tipo: str,
    *,
    excluir_id: int | None = None,
) -> list[Conflicto]:
    """Comprueba un periodo de vacaciones/baja/permiso antes de guardarlo."""
    conflictos: list[Conflicto] = []

    # 1. Solapamiento con otro periodo del mismo empleado.
    solapados = periodos_solapados(
        db, empleado.id, fecha_inicio, fecha_fin, excluir_id,
    )
    if solapados:
        s = solapados[0]
        conflictos.append(Conflicto(
            "solape", SEV_BLOQUEANTE,
            f"Se solapa con otro periodo de {empleado.nombre_completo} "
            f"({s.fecha_inicio:%d/%m/%Y}–{s.fecha_fin:%d/%m/%Y}).",
        ))

    # 2. Cupo anual de vacaciones (no aplica a bajas ni permisos).
    if tipo == TIPO_VACACIONES:
        for anio in range(fecha_inicio.year, fecha_fin.year + 1):
            consumidos = dias_vacaciones_consumidos(
                db, empleado.id, anio, excluir_id,
            )
            nuevos = _dias_en_anio(fecha_inicio, fecha_fin, anio)
            if consumidos + nuevos > empleado.dias_vacaciones_anuales:
                conflictos.append(Conflicto(
                    "cupo", SEV_BLOQUEANTE,
                    f"Supera el cupo de {empleado.dias_vacaciones_anuales} días "
                    f"de {anio}: ya tiene {consumidos} y solicita {nuevos} más.",
                ))

    # 3. Periodos no aptos del centro del empleado.
    if empleado.centro_trabajo_id is not None:
        no_aptos = (
            db.query(PeriodoNoApto)
            .filter(
                PeriodoNoApto.centro_id == empleado.centro_trabajo_id,
                PeriodoNoApto.fecha_inicio <= fecha_fin,
                PeriodoNoApto.fecha_fin >= fecha_inicio,
            )
            .all()
        )
        for na in no_aptos:
            conflictos.append(Conflicto(
                "no_apto", SEV_ADVERTENCIA,
                f"Coincide con el periodo no apto «{na.nombre}» "
                f"({na.fecha_inicio:%d/%m}–{na.fecha_fin:%d/%m}).",
            ))

    # 4. Impacto en la dotación mínima del centro.
    dias_riesgo = _dias_bajo_minimo(db, empleado, fecha_inicio, fecha_fin)
    if dias_riesgo:
        conflictos.append(Conflicto(
            "dotacion", SEV_ADVERTENCIA,
            f"{dias_riesgo} día(s) del periodo dejarían el centro por debajo "
            "de la dotación mínima prevista.",
        ))

    return conflictos
