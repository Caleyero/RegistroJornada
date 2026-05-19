"""Servicio de configuración de centros para la planificación de turnos.

Cubre tres bloques de configuración por centro:
    - Horario de apertura por día de la semana.
    - Plantillas de turno (Mañana, Tarde, Partido...).
    - Dotación de personal (mínimo/máximo) por día y turno.

Las funciones son puras sobre la sesión: no renderizan ni dependen de la
capa web.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import CentroHorarioApertura, DotacionCentro, PlantillaTurno
from app.services.diario_service import _to_minutos, _validar_hhmm


# Nombres de los días de la semana — índice 0..6 == lunes..domingo, el mismo
# criterio que `date.weekday()` y que `dias_laborables_habituales`.
DIAS_SEMANA = [
    "Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo",
]
DIAS_SEMANA_CORTO = ["L", "M", "X", "J", "V", "S", "D"]


# ---------------------------------------------------------------------------
# Horario de apertura
# ---------------------------------------------------------------------------

def horario_por_dia(db: Session, centro_id: int) -> dict[int, CentroHorarioApertura]:
    """Devuelve {dia_semana: CentroHorarioApertura} con las filas existentes."""
    filas = (
        db.query(CentroHorarioApertura)
        .filter(CentroHorarioApertura.centro_id == centro_id)
        .all()
    )
    return {f.dia_semana: f for f in filas}


def cargar_horario(db: Session, centro_id: int) -> list[CentroHorarioApertura]:
    """Lista de 7 filas (lun..dom); las no definidas se devuelven transitorias."""
    existentes = horario_por_dia(db, centro_id)
    out: list[CentroHorarioApertura] = []
    for dow in range(7):
        fila = existentes.get(dow)
        if fila is None:
            fila = CentroHorarioApertura(
                centro_id=centro_id, dia_semana=dow, cerrado=(dow == 6),
            )
        out.append(fila)
    return out


def guardar_horario(
    db: Session, centro_id: int, datos: dict[int, dict],
) -> None:
    """Upsert del horario de apertura.

    `datos` = {dow: {cerrado, apertura, inicio_pausa, fin_pausa, cierre}}.
    La pausa de mediodía (inicio_pausa/fin_pausa) es opcional: o se rellenan
    las dos o ninguna. Lanza ValueError si una hora no es HH:MM válida o si
    el orden de las horas no es coherente.
    """
    existentes = horario_por_dia(db, centro_id)
    for dow in range(7):
        d = datos.get(dow)
        if d is None:
            continue
        dia = DIAS_SEMANA[dow]
        cerrado = bool(d.get("cerrado"))
        apertura = cierre = inicio_pausa = fin_pausa = None
        if not cerrado:
            ap_raw = (d.get("apertura") or "").strip()
            ci_raw = (d.get("cierre") or "").strip()
            ini_raw = (d.get("inicio_pausa") or "").strip()
            fin_raw = (d.get("fin_pausa") or "").strip()
            # Día que solo abre por la mañana: si se rellena la apertura y la
            # hora de cierre del mediodía, pero no la reapertura ni el cierre
            # del día, se interpreta como jornada continua hasta esa hora.
            if ap_raw and ini_raw and not fin_raw and not ci_raw:
                ci_raw, ini_raw = ini_raw, ""
            apertura = _validar_hhmm(ap_raw, f"apertura {dia}")
            cierre = _validar_hhmm(ci_raw, f"cierre {dia}")
            if _to_minutos(cierre) <= _to_minutos(apertura):
                raise ValueError(
                    f"{dia}: la hora de cierre debe ser posterior a la de apertura."
                )
            if ini_raw or fin_raw:
                if not (ini_raw and fin_raw):
                    raise ValueError(
                        f"{dia}: indica la hora de cierre y de reapertura del "
                        "mediodía, o deja ambas vacías (jornada continua)."
                    )
                inicio_pausa = _validar_hhmm(ini_raw, f"cierre mediodía {dia}")
                fin_pausa = _validar_hhmm(fin_raw, f"reapertura {dia}")
                if not (
                    _to_minutos(apertura) < _to_minutos(inicio_pausa)
                    <= _to_minutos(fin_pausa) < _to_minutos(cierre)
                ):
                    raise ValueError(
                        f"{dia}: la pausa de mediodía debe quedar dentro del "
                        "horario de apertura."
                    )
        fila = existentes.get(dow)
        if fila is None:
            fila = CentroHorarioApertura(centro_id=centro_id, dia_semana=dow)
            db.add(fila)
        fila.cerrado = cerrado
        fila.apertura = apertura
        fila.cierre = cierre
        fila.inicio_pausa = inicio_pausa
        fila.fin_pausa = fin_pausa
    db.commit()


def horario_apertura_de(
    db: Session, centro_id: int, dia_semana: int,
) -> CentroHorarioApertura | None:
    """Fila de horario de apertura del centro para ese día, o None si no existe."""
    return (
        db.query(CentroHorarioApertura)
        .filter(
            CentroHorarioApertura.centro_id == centro_id,
            CentroHorarioApertura.dia_semana == dia_semana,
        )
        .one_or_none()
    )


# ---------------------------------------------------------------------------
# Plantillas de turno
# ---------------------------------------------------------------------------

def turnos_de(
    db: Session, centro_id: int, *, solo_activos: bool = False,
) -> list[PlantillaTurno]:
    """Plantillas de turno del centro ordenadas por `orden` y luego por nombre."""
    q = db.query(PlantillaTurno).filter(PlantillaTurno.centro_id == centro_id)
    if solo_activos:
        q = q.filter(PlantillaTurno.activo.is_(True))
    return q.order_by(PlantillaTurno.orden, PlantillaTurno.nombre).all()


def validar_turno(
    hora_inicio: str, hora_fin: str,
    inicio_pausa: str | None, fin_pausa: str | None,
) -> tuple[str, str, str | None, str | None]:
    """Normaliza y valida los horarios de una plantilla de turno.

    Devuelve la tupla normalizada (hora_inicio, hora_fin, inicio_pausa,
    fin_pausa). Lanza ValueError si algo no encaja.
    """
    hi = _validar_hhmm(hora_inicio, "hora de inicio")
    hf = _validar_hhmm(hora_fin, "hora de fin")
    if _to_minutos(hf) <= _to_minutos(hi):
        raise ValueError("La hora de fin debe ser posterior a la de inicio.")
    ip = fp = None
    pausa_inicio = (inicio_pausa or "").strip()
    pausa_fin = (fin_pausa or "").strip()
    if pausa_inicio or pausa_fin:
        if not (pausa_inicio and pausa_fin):
            raise ValueError(
                "Para un turno partido hay que indicar inicio y fin de la pausa."
            )
        ip = _validar_hhmm(pausa_inicio, "inicio de pausa")
        fp = _validar_hhmm(pausa_fin, "fin de pausa")
        if not (_to_minutos(hi) <= _to_minutos(ip) <= _to_minutos(fp) <= _to_minutos(hf)):
            raise ValueError(
                "La pausa debe quedar dentro del turno: "
                "inicio ≤ inicio pausa ≤ fin pausa ≤ fin."
            )
    return hi, hf, ip, fp


def turno_dentro_de_apertura(
    turno: PlantillaTurno, horario: CentroHorarioApertura | None,
) -> bool:
    """True si el turno encaja dentro del horario de apertura del centro.

    Si no hay horario de apertura definido para ese día, se considera que
    no se puede comprobar y se devuelve True (no se bloquea por falta de
    configuración).
    """
    if horario is None:
        return True
    if horario.cerrado:
        return False
    if not (horario.apertura and horario.cierre):
        return True
    ti = _to_minutos(turno.hora_inicio)
    tf = _to_minutos(turno.hora_fin)
    if not (_to_minutos(horario.apertura) <= ti and tf <= _to_minutos(horario.cierre)):
        return False
    # Si el centro cierra a mediodía, un turno que cae entero dentro de ese
    # hueco no es válido (un turno partido que lo cruza sí lo es).
    if horario.inicio_pausa and horario.fin_pausa:
        if ti >= _to_minutos(horario.inicio_pausa) and tf <= _to_minutos(horario.fin_pausa):
            return False
    return True


# ---------------------------------------------------------------------------
# Dotación
# ---------------------------------------------------------------------------

def dotacion_por_clave(
    db: Session, centro_id: int,
) -> dict[tuple[int, int], DotacionCentro]:
    """Devuelve {(plantilla_turno_id, dia_semana): DotacionCentro}."""
    filas = (
        db.query(DotacionCentro)
        .filter(DotacionCentro.centro_id == centro_id)
        .all()
    )
    return {(f.plantilla_turno_id, f.dia_semana): f for f in filas}


def matriz_dotacion(
    db: Session, centro_id: int,
) -> dict[int, dict[int, DotacionCentro]]:
    """Devuelve {turno_id: {dia_semana: DotacionCentro}} — cómodo para la UI."""
    out: dict[int, dict[int, DotacionCentro]] = {}
    filas = (
        db.query(DotacionCentro)
        .filter(DotacionCentro.centro_id == centro_id)
        .all()
    )
    for f in filas:
        out.setdefault(f.plantilla_turno_id, {})[f.dia_semana] = f
    return out


def dotacion_de(
    db: Session, centro_id: int, turno_id: int, dia_semana: int,
) -> DotacionCentro | None:
    """Dotación configurada para (centro, turno, día), o None si no hay."""
    return (
        db.query(DotacionCentro)
        .filter(
            DotacionCentro.centro_id == centro_id,
            DotacionCentro.plantilla_turno_id == turno_id,
            DotacionCentro.dia_semana == dia_semana,
        )
        .one_or_none()
    )


def guardar_dotacion(
    db: Session, centro_id: int, datos: dict[tuple[int, int], dict],
) -> None:
    """Upsert de la dotación. `datos` = {(turno_id, dow): {minimo, maximo}}.

    Una celda con mínimo y máximo a 0 se interpreta como "sin requisito" y
    elimina la fila si existía. Lanza ValueError si máximo < mínimo.
    """
    existentes = dotacion_por_clave(db, centro_id)
    for (turno_id, dow), v in datos.items():
        minimo = int(v.get("minimo") or 0)
        maximo = int(v.get("maximo") or 0)
        if minimo < 0 or maximo < 0:
            raise ValueError("La dotación no puede ser negativa.")
        if maximo < minimo:
            raise ValueError(
                f"{DIAS_SEMANA[dow]}: el máximo no puede ser menor que el mínimo."
            )
        fila = existentes.get((turno_id, dow))
        if minimo == 0 and maximo == 0:
            if fila is not None:
                db.delete(fila)
            continue
        if fila is None:
            fila = DotacionCentro(
                centro_id=centro_id, plantilla_turno_id=turno_id, dia_semana=dow,
            )
            db.add(fila)
        fila.minimo = minimo
        fila.maximo = maximo
    db.commit()
