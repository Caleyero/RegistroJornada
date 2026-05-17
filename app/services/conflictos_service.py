"""Núcleo del planificador asistido de turnos.

Tres capacidades, todas puras sobre la sesión:

    - `validar_asignacion()`  — detecta conflictos al asignar un turno.
    - `calcular_cobertura()`  — compara lo planificado con la dotación.
    - `buscar_sustitutos()`   — propone candidatos ordenados por idoneidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models import (
    CentroTrabajo, Empleado, PeriodoVacaciones, PlantillaTurno,
    RegistroDiario, TurnoPlanificado,
)
from app.models.periodo_vacaciones import TIPO_ETIQUETAS
from app.models.registro_diario import (
    TIPO_AUSENCIA, TIPO_FESTIVO, TIPO_VACACIONES,
)
from app.services import turnos_service
from app.services.diario_service import _to_minutos, dia_fuera_de_periodo


# Descanso mínimo entre jornadas — art. 34.3 ET: 12 horas.
DESCANSO_MINIMO_MIN = 12 * 60

SEV_BLOQUEANTE = "bloqueante"
SEV_ADVERTENCIA = "advertencia"


@dataclass
class Conflicto:
    tipo: str
    severidad: str
    mensaje: str

    @property
    def es_bloqueante(self) -> bool:
        return self.severidad == SEV_BLOQUEANTE


def hay_bloqueante(conflictos: list[Conflicto]) -> bool:
    """True si alguno de los conflictos impide la asignación."""
    return any(c.es_bloqueante for c in conflictos)


# ---------------------------------------------------------------------------
# Consultas auxiliares
# ---------------------------------------------------------------------------

def periodo_vacaciones_en(
    db: Session, empleado_id: int, fecha: date,
) -> PeriodoVacaciones | None:
    """Periodo de vacaciones/baja/permiso del empleado que cubre `fecha`."""
    return (
        db.query(PeriodoVacaciones)
        .filter(
            PeriodoVacaciones.empleado_id == empleado_id,
            PeriodoVacaciones.fecha_inicio <= fecha,
            PeriodoVacaciones.fecha_fin >= fecha,
        )
        .first()
    )


def turno_planificado_en(
    db: Session, empleado_id: int, fecha: date,
) -> TurnoPlanificado | None:
    """Turno ya planificado para el empleado en esa fecha, si lo hay."""
    return (
        db.query(TurnoPlanificado)
        .filter(
            TurnoPlanificado.empleado_id == empleado_id,
            TurnoPlanificado.fecha == fecha,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Validación de una asignación
# ---------------------------------------------------------------------------

def validar_asignacion(
    db: Session,
    empleado: Empleado,
    fecha: date,
    plantilla_turno: PlantillaTurno,
    centro: CentroTrabajo,
    *,
    excluir_turno_id: int | None = None,
) -> list[Conflicto]:
    """Lista los conflictos de asignar `plantilla_turno` a `empleado`.

    `excluir_turno_id` permite revalidar un turno existente sin que se
    detecte a sí mismo como doble asignación.
    """
    conflictos: list[Conflicto] = []

    # 1. Fuera del periodo de alta/baja del empleado.
    if dia_fuera_de_periodo(empleado, fecha):
        conflictos.append(Conflicto(
            "fuera_periodo", SEV_BLOQUEANTE,
            f"{empleado.nombre_completo} no está de alta en esa fecha.",
        ))

    # 2. Empleado de vacaciones, baja o permiso.
    pv = periodo_vacaciones_en(db, empleado.id, fecha)
    if pv is not None:
        etq = TIPO_ETIQUETAS.get(pv.tipo, pv.tipo).lower()
        conflictos.append(Conflicto(
            "vacaciones", SEV_BLOQUEANTE,
            f"{empleado.nombre_completo} tiene {etq} "
            f"del {pv.fecha_inicio:%d/%m} al {pv.fecha_fin:%d/%m}.",
        ))

    # 3. Doble asignación (además del UniqueConstraint de BD).
    otro = turno_planificado_en(db, empleado.id, fecha)
    if otro is not None and otro.id != excluir_turno_id:
        conflictos.append(Conflicto(
            "doble_asignacion", SEV_BLOQUEANTE,
            f"{empleado.nombre_completo} ya tiene un turno asignado ese día.",
        ))

    # 4. ¿Puede el empleado cubrir este centro?
    if centro.id not in empleado.ids_centros_cubribles_efectivos:
        if empleado.disponible_desplazamiento:
            conflictos.append(Conflicto(
                "centro_no_habitual", SEV_ADVERTENCIA,
                f"{centro.nombre} no figura entre los centros de "
                f"{empleado.nombre_completo}, pero admite desplazamiento.",
            ))
        else:
            conflictos.append(Conflicto(
                "centro_no_cubrible", SEV_BLOQUEANTE,
                f"{empleado.nombre_completo} no puede cubrir {centro.nombre}: "
                "no es su centro ni admite desplazamiento.",
            ))

    # 5. ¿El turno cae dentro del horario de apertura del centro?
    horario = turnos_service.horario_apertura_de(db, centro.id, fecha.weekday())
    dia_nombre = turnos_service.DIAS_SEMANA[fecha.weekday()].lower()
    if horario is not None and horario.cerrado:
        conflictos.append(Conflicto(
            "centro_cerrado", SEV_BLOQUEANTE,
            f"{centro.nombre} permanece cerrado los {dia_nombre}.",
        ))
    elif not turnos_service.turno_dentro_de_apertura(plantilla_turno, horario):
        conflictos.append(Conflicto(
            "fuera_horario", SEV_BLOQUEANTE,
            f"El turno {plantilla_turno.hora_inicio}–{plantilla_turno.hora_fin} "
            f"cae fuera del horario de apertura de {centro.nombre}.",
        ))

    # 6. Descanso mínimo de 12 h entre jornadas.
    prev = turno_planificado_en(db, empleado.id, fecha - timedelta(days=1))
    if prev is not None and prev.id != excluir_turno_id:
        descanso = (
            24 * 60 - _to_minutos(prev.hora_fin)
            + _to_minutos(plantilla_turno.hora_inicio)
        )
        if descanso < DESCANSO_MINIMO_MIN:
            conflictos.append(Conflicto(
                "descanso", SEV_ADVERTENCIA,
                f"Solo {descanso // 60} h {descanso % 60:02d} m de descanso "
                "desde el turno del día anterior (mínimo legal 12 h).",
            ))
    sig = turno_planificado_en(db, empleado.id, fecha + timedelta(days=1))
    if sig is not None and sig.id != excluir_turno_id:
        descanso = (
            24 * 60 - _to_minutos(plantilla_turno.hora_fin)
            + _to_minutos(sig.hora_inicio)
        )
        if descanso < DESCANSO_MINIMO_MIN:
            conflictos.append(Conflicto(
                "descanso", SEV_ADVERTENCIA,
                f"Solo {descanso // 60} h {descanso % 60:02d} m de descanso "
                "hasta el turno del día siguiente (mínimo legal 12 h).",
            ))

    # 7. El registro diario de ese día ya está marcado como no trabajado.
    rd = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.empleado_id == empleado.id,
            RegistroDiario.fecha == fecha,
        )
        .first()
    )
    if rd is not None and rd.tipo in (TIPO_FESTIVO, TIPO_VACACIONES, TIPO_AUSENCIA):
        conflictos.append(Conflicto(
            "registro_diario", SEV_ADVERTENCIA,
            f"El registro diario de ese día ya consta como «{rd.tipo}».",
        ))

    return conflictos


# ---------------------------------------------------------------------------
# Cobertura (semáforo de dotación)
# ---------------------------------------------------------------------------

@dataclass
class CoberturaTurno:
    turno: PlantillaTurno
    planificados: int
    minimo: int
    maximo: int
    semaforo: str  # 'verde' | 'ambar' | 'rojo' | 'libre'

    @property
    def texto(self) -> str:
        if self.semaforo == "libre":
            return f"{self.planificados} · sin dotación"
        return f"{self.planificados} / {self.minimo}–{self.maximo}"


def calcular_cobertura(
    db: Session, centro: CentroTrabajo, fecha: date,
) -> dict[int, CoberturaTurno]:
    """Devuelve {turno_id: CoberturaTurno} para el centro y la fecha dados."""
    dow = fecha.weekday()
    turnos = turnos_service.turnos_de(db, centro.id, solo_activos=True)

    conteo: dict[int, int] = {}
    filas = (
        db.query(TurnoPlanificado)
        .filter(
            TurnoPlanificado.centro_id == centro.id,
            TurnoPlanificado.fecha == fecha,
        )
        .all()
    )
    for f in filas:
        if f.plantilla_turno_id is not None:
            conteo[f.plantilla_turno_id] = conteo.get(f.plantilla_turno_id, 0) + 1

    out: dict[int, CoberturaTurno] = {}
    for t in turnos:
        dot = turnos_service.dotacion_de(db, centro.id, t.id, dow)
        minimo = dot.minimo if dot else 0
        maximo = dot.maximo if dot else 0
        n = conteo.get(t.id, 0)
        if minimo == 0 and maximo == 0:
            semaforo = "libre"
        elif n < minimo:
            semaforo = "rojo"
        elif maximo and n > maximo:
            semaforo = "ambar"
        else:
            semaforo = "verde"
        out[t.id] = CoberturaTurno(t, n, minimo, maximo, semaforo)
    return out


# ---------------------------------------------------------------------------
# Buscador de sustitutos
# ---------------------------------------------------------------------------

@dataclass
class Candidato:
    empleado: Empleado
    es_centro_propio: bool
    score: float
    motivos: list[str] = field(default_factory=list)
    conflictos: list[Conflicto] = field(default_factory=list)

    @property
    def tiene_bloqueante(self) -> bool:
        return hay_bloqueante(self.conflictos)


def _empleados_que_cubren(
    db: Session, centro: CentroTrabajo,
) -> dict[int, Empleado]:
    """Empleados activos que pueden cubrir el centro (propios + cubridores)."""
    out: dict[int, Empleado] = {}
    propios = (
        db.query(Empleado)
        .filter(
            Empleado.centro_trabajo_id == centro.id,
            Empleado.activo.is_(True),
        )
        .all()
    )
    for e in propios:
        out[e.id] = e
    for e in centro.empleados_cubridores:
        if e.activo:
            out[e.id] = e
    return out


def buscar_sustitutos(
    db: Session,
    centro: CentroTrabajo,
    fecha: date,
    plantilla_turno: PlantillaTurno,
) -> list[Candidato]:
    """Candidatos disponibles para cubrir el turno, ordenados por idoneidad.

    Quedan excluidos quienes ese día están de vacaciones/baja, ya tienen
    turno o están fuera de su periodo de alta. El resto se puntúa: primero
    los del propio centro, después los que no arrastran avisos, los que
    admiten horas extras y los que llevan menos turnos esa semana.
    """
    lunes = fecha - timedelta(days=fecha.weekday())
    domingo = lunes + timedelta(days=6)

    candidatos: list[Candidato] = []
    for e in _empleados_que_cubren(db, centro).values():
        if dia_fuera_de_periodo(e, fecha):
            continue
        if periodo_vacaciones_en(db, e.id, fecha) is not None:
            continue
        if turno_planificado_en(db, e.id, fecha) is not None:
            continue

        es_propio = e.centro_trabajo_id == centro.id
        conflictos = validar_asignacion(db, e, fecha, plantilla_turno, centro)
        turnos_semana = (
            db.query(TurnoPlanificado)
            .filter(
                TurnoPlanificado.empleado_id == e.id,
                TurnoPlanificado.fecha >= lunes,
                TurnoPlanificado.fecha <= domingo,
            )
            .count()
        )

        motivos: list[str] = []
        score = 0.0
        if es_propio:
            score += 100
            motivos.append("Plantilla de este centro")
        else:
            motivos.append("Habilitado para cubrir este centro")
        if e.admite_horas_extras:
            score += 10
            motivos.append("Admite horas extras")
        if not conflictos:
            score += 20
        score -= 5 * turnos_semana
        motivos.append(f"{turnos_semana} turno(s) esta semana")

        candidatos.append(Candidato(
            empleado=e, es_centro_propio=es_propio, score=score,
            motivos=motivos, conflictos=conflictos,
        ))

    candidatos.sort(
        key=lambda c: (c.tiene_bloqueante, -c.score, c.empleado.apellidos),
    )
    return candidatos
