"""Lógica del registro diario de jornada (art. 34.9 ET).

Implementa:

- Auto-relleno perezoso del mes a partir del horario habitual del empleado
  y del calendario asturiano de festivos (`asegurar_mes`).
- Upsert de un día concreto desde la UI (`upsert_dia`), validando horario.
- Conversión de la colección diaria mensual al payload que espera
  `pdf_service.generar_pdf_registro_mensual()` (`dias_a_payload_pdf`).
- Cierre / reapertura del mes (`cerrar_mes`, `reabrir_mes`).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import Empleado, RegistroDiario
from app.models.registro_diario import (
    FUENTE_AUTO, FUENTE_MANUAL,
    TIPO_AUSENCIA, TIPO_FESTIVO, TIPO_TRABAJADO, TIPO_VACACIONES,
    TIPOS_VALIDOS,
)
from app.services.festivos import FESTIVOS_ASTURIAS


# ---------------------------------------------------------------------------
# Defaults — se aplican cuando el empleado no tiene horario habitual en perfil
# o cuando se llama desde un contexto sin perfil. Alineados con los defaults
# del wizard mensual (app/templates/registros/wizard.html:546-547).
# ---------------------------------------------------------------------------
DEFAULT_INICIO_JORNADA = "10:00"
DEFAULT_INICIO_PAUSA = "14:00"
DEFAULT_FIN_PAUSA = "14:30"
DEFAULT_FIN_JORNADA = "18:30"
DEFAULT_DIAS_LABORABLES = [0, 1, 2, 3, 4]  # L-V

_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")


# ---------------------------------------------------------------------------
# Helpers de horario
# ---------------------------------------------------------------------------

def horario_tipo_de_empleado(empleado: Empleado) -> dict[str, str]:
    """Devuelve los 4 horarios "tipo" del empleado, con defaults si faltan.

    Si el empleado tiene todos los campos del perfil rellenos, se usan tal cual.
    Si alguno es None, se completa con los defaults globales.
    """
    return {
        "inicio_jornada": empleado.inicio_jornada or DEFAULT_INICIO_JORNADA,
        "inicio_pausa": empleado.inicio_pausa or DEFAULT_INICIO_PAUSA,
        "fin_pausa": empleado.fin_pausa or DEFAULT_FIN_PAUSA,
        "fin_jornada": empleado.fin_jornada or DEFAULT_FIN_JORNADA,
    }


def dias_laborables_de_empleado(empleado: Empleado) -> list[int]:
    """Devuelve la lista [0..6] de DOW laborables del empleado o L-V por defecto."""
    dias = empleado.dias_laborables_habituales
    if not dias:
        return list(DEFAULT_DIAS_LABORABLES)
    return sorted({int(d) for d in dias if 0 <= int(d) <= 6})


def _to_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _validar_hhmm(valor: str, etiqueta: str) -> str:
    v = (valor or "").strip()
    if not _HHMM_RE.match(v):
        raise ValueError(f"{etiqueta}: formato debe ser HH:MM (recibido: {valor!r}).")
    h, m = v.split(":")
    if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError(f"{etiqueta}: hora fuera de rango ({valor}).")
    return v


# ---------------------------------------------------------------------------
# Auto-relleno del mes
# ---------------------------------------------------------------------------

def _ultimo_dia_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def _hoy() -> date:
    """Indirección para poder mockear en tests futuros."""
    return date.today()


def cargar_mes(
    db: Session, empleado: Empleado, anio: int, mes: int,
) -> list[RegistroDiario]:
    """Devuelve los `RegistroDiario` existentes del mes, ordenados por fecha.

    Ya **no** crea filas automáticamente — ni festivos, ni descansos, ni nada.
    El art. 34.9 ET pide registro fidedigno y solo el empleado puede dar
    fe del día. Festivos y descansos se infieren en la UI y en el PDF a
    partir del calendario asturiano y del perfil del empleado, pero sin
    persistir filas.
    """
    return (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.empleado_id == empleado.id,
            RegistroDiario.fecha >= date(anio, mes, 1),
            RegistroDiario.fecha <= date(anio, mes, _ultimo_dia_mes(anio, mes)),
        )
        .order_by(RegistroDiario.fecha.asc())
        .all()
    )


# Alias retrocompatible para no romper imports antiguos durante el cambio.
asegurar_mes = cargar_mes


def dia_fuera_de_periodo(empleado: Empleado, fecha: date) -> bool:
    """True si la fecha es anterior al alta o posterior a la baja del empleado."""
    if empleado.fecha_alta and fecha < empleado.fecha_alta:
        return True
    if empleado.fecha_baja and fecha > empleado.fecha_baja:
        return True
    return False


def pendientes_laborables_pasados(
    empleado: Empleado, anio: int, mes: int, dias: list[RegistroDiario],
    hoy: date | None = None,
) -> list[date]:
    """Devuelve fechas laborables (según perfil) <= hoy del mes sin fila.

    Uso: marcado visual en el calendario (celdas rojas "pendiente_pasado")
    y aviso en pantalla. Para validar el cierre del mes usa
    `pendientes_laborables_para_cierre`, que exige el mes completo.

    Reglas:
    - Sólo cuenta días en `dias_laborables_habituales` del empleado.
    - Excluye festivos del calendario asturiano (no requieren confirmación
      expresa; el PDF los recoge automáticamente al cerrar).
    - Excluye fechas anteriores a `fecha_alta` o posteriores a `fecha_baja`
      del empleado.
    """
    if hoy is None:
        hoy = _hoy()
    dias_laborables = set(dias_laborables_de_empleado(empleado))
    fechas_con_fila = {d.fecha for d in dias}
    fin = min(hoy, date(anio, mes, _ultimo_dia_mes(anio, mes)))

    pendientes: list[date] = []
    for dia in range(1, fin.day + 1):
        fecha = date(anio, mes, dia)
        if dia_fuera_de_periodo(empleado, fecha):
            continue
        if fecha in fechas_con_fila:
            continue
        if fecha.weekday() not in dias_laborables:
            continue
        if fecha.isoformat() in FESTIVOS_ASTURIAS:
            continue
        pendientes.append(fecha)
    return pendientes


def pendientes_laborables_para_cierre(
    empleado: Empleado, anio: int, mes: int, dias: list[RegistroDiario],
) -> list[date]:
    """Fechas laborables del mes (completo) sin confirmar, bloqueantes del cierre.

    Igual que `pendientes_laborables_pasados` pero exige el mes entero:
    no se puede cerrar un mes a medias salvo cese del empleado. La
    excepción del cese se aplica automáticamente porque
    `dia_fuera_de_periodo` excluye los días posteriores a `fecha_baja`.
    """
    dias_laborables = set(dias_laborables_de_empleado(empleado))
    fechas_con_fila = {d.fecha for d in dias}
    pendientes: list[date] = []
    for dia in range(1, _ultimo_dia_mes(anio, mes) + 1):
        fecha = date(anio, mes, dia)
        if dia_fuera_de_periodo(empleado, fecha):
            continue
        if fecha in fechas_con_fila:
            continue
        if fecha.weekday() not in dias_laborables:
            continue
        if fecha.isoformat() in FESTIVOS_ASTURIAS:
            continue
        pendientes.append(fecha)
    return pendientes


# ---------------------------------------------------------------------------
# Upsert de un día
# ---------------------------------------------------------------------------

@dataclass
class DiaPayload:
    tipo: str
    inicio_jornada: str | None = None
    inicio_pausa: str | None = None
    fin_pausa: str | None = None
    fin_jornada: str | None = None
    observaciones: str | None = None


def upsert_dia(
    db: Session, empleado: Empleado, fecha: date, payload: DiaPayload,
    *, fuente: str = FUENTE_MANUAL,
) -> RegistroDiario:
    """Crea o actualiza el `RegistroDiario` de (empleado, fecha)."""
    if payload.tipo not in TIPOS_VALIDOS:
        raise ValueError(
            f"Tipo de día inválido: {payload.tipo!r}. "
            f"Valores válidos: {sorted(TIPOS_VALIDOS)}."
        )
    if dia_fuera_de_periodo(empleado, fecha):
        alta = empleado.fecha_alta.strftime("%d/%m/%Y") if empleado.fecha_alta else "—"
        baja = empleado.fecha_baja.strftime("%d/%m/%Y") if empleado.fecha_baja else "—"
        raise ValueError(
            f"La fecha {fecha.strftime('%d/%m/%Y')} está fuera del periodo de "
            f"alta del empleado (alta: {alta}, baja: {baja})."
        )

    horarios = (
        payload.inicio_jornada, payload.inicio_pausa,
        payload.fin_pausa, payload.fin_jornada,
    )
    if payload.tipo == TIPO_TRABAJADO:
        if not all(horarios):
            raise ValueError(
                "Para un día trabajado hay que cumplimentar los 4 horarios "
                "(inicio jornada, inicio pausa, fin pausa, fin jornada)."
            )
        ij = _validar_hhmm(payload.inicio_jornada, "inicio jornada")
        ip = _validar_hhmm(payload.inicio_pausa, "inicio pausa")
        fp = _validar_hhmm(payload.fin_pausa, "fin pausa")
        fj = _validar_hhmm(payload.fin_jornada, "fin jornada")
        if not (_to_minutos(ij) <= _to_minutos(ip) <= _to_minutos(fp) <= _to_minutos(fj)):
            raise ValueError(
                "El horario no es coherente: deben cumplirse "
                "inicio ≤ inicio pausa ≤ fin pausa ≤ fin jornada."
            )
    else:
        # En cualquier tipo no laborable los horarios se descartan.
        ij = ip = fp = fj = None

    existente = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.empleado_id == empleado.id,
            RegistroDiario.fecha == fecha,
        )
        .first()
    )
    if existente and existente.cerrado:
        raise PermissionError(
            f"El día {fecha.strftime('%d/%m/%Y')} está cerrado y no puede "
            "modificarse. Pide al administrador que reabra el mes."
        )

    obs = (payload.observaciones or "").strip() or None

    if existente is None:
        registro = RegistroDiario(
            empleado_id=empleado.id, fecha=fecha,
            tipo=payload.tipo, fuente=fuente,
            inicio_jornada=ij, inicio_pausa=ip, fin_pausa=fp, fin_jornada=fj,
            observaciones=obs,
        )
        db.add(registro)
    else:
        registro = existente
        registro.tipo = payload.tipo
        registro.inicio_jornada = ij
        registro.inicio_pausa = ip
        registro.fin_pausa = fp
        registro.fin_jornada = fj
        registro.observaciones = obs
        registro.fuente = fuente

    db.commit()
    db.refresh(registro)
    return registro


# ---------------------------------------------------------------------------
# Conversión a payload del PDF
# ---------------------------------------------------------------------------

def dias_a_payload_pdf(
    empleado: Empleado, anio: int, mes: int, dias: list[RegistroDiario],
) -> dict[str, Any]:
    """Convierte la lista de días en el dict que consume `RegistroPayload`.

    Como ahora la BD sólo guarda lo que el usuario confirmó expresamente,
    los festivos y los días fuera de periodo de alta/baja se **infieren** y
    se añaden al payload en este punto:

    - `festivos` = festivos del calendario asturiano del mes que NO han sido
      sobrescritos por el empleado con otro tipo (trabajado, vacaciones, etc.)
      MÁS los días que el empleado haya marcado expresamente como festivo.
    - `ausencias` = ausencias confirmadas + días fuera del periodo alta/baja
      (etiquetados como "Antes de alta" / "Tras baja").

    El PDF resultante refleja jornada confirmada, infiere lo objetivo y deja
    claras las fechas fuera del periodo laboral del empleado.
    """
    horario = horario_tipo_de_empleado(empleado)
    dias_laborables = dias_laborables_de_empleado(empleado)
    fechas_con_fila = {d.fecha for d in dias}

    festivos: dict[str, str] = {}
    vacaciones: list[str] = []
    ausencias: dict[str, str] = {}
    overrides: dict[str, dict[str, str]] = {}

    # 1) Procesar filas confirmadas
    for d in dias:
        iso = d.fecha.isoformat()
        if d.tipo == TIPO_FESTIVO:
            festivos[iso] = d.observaciones or "Festivo"
        elif d.tipo == TIPO_VACACIONES:
            vacaciones.append(iso)
        elif d.tipo == TIPO_AUSENCIA:
            ausencias[iso] = d.observaciones or "Ausencia justificada"
        elif d.tipo == TIPO_TRABAJADO:
            override = {
                "inicio_jornada": d.inicio_jornada or "",
                "inicio_pausa": d.inicio_pausa or "",
                "fin_pausa": d.fin_pausa or "",
                "fin_jornada": d.fin_jornada or "",
            }
            if override != horario:
                overrides[iso] = override
        # TIPO_DESCANSO: nada — coincide con dias_laborables del perfil.

    # 2) Inferir festivos del calendario para las fechas SIN fila confirmada.
    for dia in range(1, _ultimo_dia_mes(anio, mes) + 1):
        fecha = date(anio, mes, dia)
        if fecha in fechas_con_fila:
            continue
        if dia_fuera_de_periodo(empleado, fecha):
            continue
        iso = fecha.isoformat()
        descripcion = FESTIVOS_ASTURIAS.get(iso)
        if descripcion:
            festivos[iso] = descripcion

    # 3) Marcar días fuera de periodo (antes de alta / tras baja) como ausencia
    #    para que el PDF los anote en observaciones en vez de pintar horario.
    for dia in range(1, _ultimo_dia_mes(anio, mes) + 1):
        fecha = date(anio, mes, dia)
        iso = fecha.isoformat()
        if empleado.fecha_alta and fecha < empleado.fecha_alta:
            ausencias.setdefault(
                iso, f"Antes de alta ({empleado.fecha_alta.strftime('%d/%m/%Y')})",
            )
        elif empleado.fecha_baja and fecha > empleado.fecha_baja:
            ausencias.setdefault(
                iso, f"Tras baja ({empleado.fecha_baja.strftime('%d/%m/%Y')})",
            )

    return {
        "empleado_id": empleado.id,
        "anio": anio,
        "mes": mes,
        "dias_laborables": dias_laborables,
        **horario,
        "festivos": festivos,
        "vacaciones": vacaciones,
        "ausencias": ausencias,
        "overrides_horario": overrides,
    }


# ---------------------------------------------------------------------------
# Cierre / reapertura del mes
# ---------------------------------------------------------------------------

def cerrar_mes(db: Session, empleado: Empleado, anio: int, mes: int) -> int:
    """Marca como `cerrado=True` todos los días del mes/empleado. Devuelve nº filas."""
    updated = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.empleado_id == empleado.id,
            RegistroDiario.fecha >= date(anio, mes, 1),
            RegistroDiario.fecha <= date(anio, mes, _ultimo_dia_mes(anio, mes)),
        )
        .update({RegistroDiario.cerrado: True}, synchronize_session=False)
    )
    db.commit()
    return updated


def reabrir_mes(db: Session, empleado: Empleado, anio: int, mes: int) -> int:
    updated = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.empleado_id == empleado.id,
            RegistroDiario.fecha >= date(anio, mes, 1),
            RegistroDiario.fecha <= date(anio, mes, _ultimo_dia_mes(anio, mes)),
        )
        .update({RegistroDiario.cerrado: False}, synchronize_session=False)
    )
    db.commit()
    return updated


def mes_esta_cerrado(dias: list[RegistroDiario]) -> bool:
    """True si hay al menos un día y todos están cerrados."""
    return bool(dias) and all(d.cerrado for d in dias)


# ---------------------------------------------------------------------------
# Revertir un día a "pendiente" (borrar la fila)
# ---------------------------------------------------------------------------

def borrar_dia(db: Session, empleado: Empleado, fecha: date) -> bool:
    """Borra la fila `RegistroDiario` de (empleado, fecha) → vuelve a pendiente.

    Devuelve True si había fila y se borró. Lanza:
    - `ValueError` si la fecha está fuera del periodo de alta/baja del empleado.
    - `PermissionError` si la fila existe pero está `cerrado=True`.
    """
    if dia_fuera_de_periodo(empleado, fecha):
        raise ValueError(
            f"La fecha {fecha.strftime('%d/%m/%Y')} está fuera del periodo de "
            f"alta del empleado."
        )
    existente = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.empleado_id == empleado.id,
            RegistroDiario.fecha == fecha,
        )
        .first()
    )
    if existente is None:
        return False
    if existente.cerrado:
        raise PermissionError(
            f"El día {fecha.strftime('%d/%m/%Y')} pertenece a un mes cerrado "
            "y no puede revertirse. Pide al administrador que reabra el mes."
        )
    db.delete(existente)
    db.commit()
    return True


def borrar_dias_bulk(
    db: Session, empleado: Empleado, fechas: list[date],
) -> dict[str, Any]:
    """Borra varios `RegistroDiario` en bloque.

    Devuelve `{borrados, errores}` siguiendo la misma convención que
    `upsert_dias_bulk`.
    """
    borrados = 0
    errores: list[tuple[str, str]] = []
    for fecha in fechas:
        try:
            if borrar_dia(db, empleado, fecha):
                borrados += 1
        except (ValueError, PermissionError) as exc:
            errores.append((fecha.isoformat(), str(exc)))
    return {"borrados": borrados, "errores": errores}


# ---------------------------------------------------------------------------
# Upsert masivo (bulk) — selección múltiple desde el calendario
# ---------------------------------------------------------------------------

def upsert_dias_bulk(
    db: Session, empleado: Empleado, fechas: list[date], payload: DiaPayload,
) -> dict[str, Any]:
    """Aplica `payload` a cada fecha de la lista vía `upsert_dia`.

    Devuelve un dict con `aplicados` (nº de filas creadas o actualizadas) y
    `errores` (lista de tuplas (fecha_iso, mensaje)) para que el router lo
    devuelva al cliente. La operación es transaccional por día: si una fecha
    falla, las demás siguen.
    """
    aplicados = 0
    errores: list[tuple[str, str]] = []
    for fecha in fechas:
        try:
            upsert_dia(db, empleado, fecha, payload)
            aplicados += 1
        except (ValueError, PermissionError) as exc:
            errores.append((fecha.isoformat(), str(exc)))
    return {"aplicados": aplicados, "errores": errores}
