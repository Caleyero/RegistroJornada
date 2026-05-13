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
    FUENTE_AUTO, FUENTE_MANUAL, FUENTE_WIZARD,
    TIPO_AUSENCIA, TIPO_DESCANSO, TIPO_FESTIVO, TIPO_TRABAJADO, TIPO_VACACIONES,
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


def asegurar_mes(
    db: Session, empleado: Empleado, anio: int, mes: int,
) -> list[RegistroDiario]:
    """Auto-rellena los días objetivos (festivo / descanso semanal) del mes.

    Cumple con el art. 34.9 ET: **NO** crea filas de tipo `trabajado` por su
    cuenta — el empleado debe confirmarlas expresamente. Sí crea
    automáticamente:

    - **Festivos** del calendario asturiano: son hechos públicos, no requieren
      acto del trabajador.
    - **Descansos semanales** (DOW no laborable según el perfil del empleado):
      son ausencia de obligación, no una jornada que firmar.

    Se ejecuta sobre **todo el mes** (no se limita a "hasta hoy"): si miramos
    mayo en abril, ya queremos ver el 1 de mayo marcado como festivo.

    Los días laborables que aún no están confirmados se dejan sin fila para
    que la UI los muestre como "Pendiente" / "Por confirmar".

    Es idempotente: la unique constraint `(empleado_id, fecha)` cubre las
    re-ejecuciones.
    """
    dias_laborables = set(dias_laborables_de_empleado(empleado))

    existentes = {
        r.fecha: r for r in (
            db.query(RegistroDiario)
            .filter(
                RegistroDiario.empleado_id == empleado.id,
                RegistroDiario.fecha >= date(anio, mes, 1),
                RegistroDiario.fecha <= date(anio, mes, _ultimo_dia_mes(anio, mes)),
            )
            .all()
        )
    }

    nuevos: list[RegistroDiario] = []

    for dia in range(1, _ultimo_dia_mes(anio, mes) + 1):
        fecha = date(anio, mes, dia)
        if fecha in existentes:
            continue

        iso = fecha.isoformat()
        descripcion_festivo = FESTIVOS_ASTURIAS.get(iso)
        if descripcion_festivo:
            nuevos.append(RegistroDiario(
                empleado_id=empleado.id, fecha=fecha,
                tipo=TIPO_FESTIVO, fuente=FUENTE_AUTO,
                observaciones=descripcion_festivo,
            ))
            continue

        if fecha.weekday() not in dias_laborables:
            nuevos.append(RegistroDiario(
                empleado_id=empleado.id, fecha=fecha,
                tipo=TIPO_DESCANSO, fuente=FUENTE_AUTO,
            ))
            continue

        # Día laborable: no se crea fila — el empleado lo confirmará a mano.

    if nuevos:
        db.add_all(nuevos)
        db.commit()

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


def pendientes_laborables_pasados(
    empleado: Empleado, anio: int, mes: int, dias: list[RegistroDiario],
    hoy: date | None = None,
) -> list[date]:
    """Devuelve fechas laborables (según perfil) <= hoy del mes sin fila.

    Sólo cuenta días en `dias_laborables_habituales` del empleado y excluye
    festivos del calendario asturiano (que sí se auto-marcan). Es la lista
    que el empleado tiene pendiente de confirmar.
    """
    if hoy is None:
        hoy = _hoy()
    dias_laborables = set(dias_laborables_de_empleado(empleado))
    fechas_con_fila = {d.fecha for d in dias}
    fin = min(hoy, date(anio, mes, _ultimo_dia_mes(anio, mes)))

    pendientes: list[date] = []
    for dia in range(1, fin.day + 1):
        fecha = date(anio, mes, dia)
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
            f"El día {fecha.isoformat()} está cerrado y no puede modificarse. "
            "Pide al administrador que reabra el mes."
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

    Devuelve un diccionario con todos los campos que `_upsert_registro` y
    `pdf_service.generar_pdf_registro_mensual` necesitan: horario tipo del
    empleado, días laborables, eventos (festivos / vacaciones / ausencias) y
    overrides por día.
    """
    horario = horario_tipo_de_empleado(empleado)
    dias_laborables = dias_laborables_de_empleado(empleado)

    festivos: dict[str, str] = {}
    vacaciones: list[str] = []
    ausencias: dict[str, str] = {}
    overrides: dict[str, dict[str, str]] = {}

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
# Sincronización inversa: tras un PDF del wizard, alinear los días
# ---------------------------------------------------------------------------

def sincronizar_desde_wizard(
    db: Session, empleado: Empleado, anio: int, mes: int,
    payload: dict[str, Any],
) -> None:
    """Vuelca un payload del wizard mensual sobre los `RegistroDiario` del mes.

    Para cada día del mes hasta el último día:
      - Si está en `festivos` → tipo festivo con esa descripción.
      - Si está en `vacaciones` → tipo vacaciones.
      - Si está en `ausencias` → tipo ausencia con esa observación.
      - Si su DOW no está en `dias_laborables` → tipo descanso.
      - En caso contrario → tipo trabajado con horario tipo del payload, o el
        override si existe para esa fecha.

    Todos los días sincronizados quedan `cerrado=True` y `fuente='wizard'`.
    """
    festivos = dict(payload.get("festivos") or {})
    vacaciones = set(payload.get("vacaciones") or [])
    ausencias = dict(payload.get("ausencias") or {})
    overrides = dict(payload.get("overrides_horario") or {})
    dias_laborables = set(payload.get("dias_laborables") or DEFAULT_DIAS_LABORABLES)

    horario_tipo = {
        "inicio_jornada": payload.get("inicio_jornada") or DEFAULT_INICIO_JORNADA,
        "inicio_pausa": payload.get("inicio_pausa") or DEFAULT_INICIO_PAUSA,
        "fin_pausa": payload.get("fin_pausa") or DEFAULT_FIN_PAUSA,
        "fin_jornada": payload.get("fin_jornada") or DEFAULT_FIN_JORNADA,
    }

    existentes = {
        r.fecha: r for r in (
            db.query(RegistroDiario)
            .filter(
                RegistroDiario.empleado_id == empleado.id,
                RegistroDiario.fecha >= date(anio, mes, 1),
                RegistroDiario.fecha <= date(anio, mes, _ultimo_dia_mes(anio, mes)),
            )
            .all()
        )
    }

    for dia in range(1, _ultimo_dia_mes(anio, mes) + 1):
        fecha = date(anio, mes, dia)
        iso = fecha.isoformat()

        if iso in festivos:
            tipo, obs = TIPO_FESTIVO, festivos[iso]
            horarios = (None, None, None, None)
        elif iso in vacaciones:
            tipo, obs = TIPO_VACACIONES, None
            horarios = (None, None, None, None)
        elif iso in ausencias:
            tipo, obs = TIPO_AUSENCIA, ausencias[iso]
            horarios = (None, None, None, None)
        elif fecha.weekday() not in dias_laborables:
            tipo, obs = TIPO_DESCANSO, None
            horarios = (None, None, None, None)
        else:
            tipo, obs = TIPO_TRABAJADO, None
            ov = overrides.get(iso)
            base = ov if ov else horario_tipo
            horarios = (
                base["inicio_jornada"], base["inicio_pausa"],
                base["fin_pausa"], base["fin_jornada"],
            )

        ij, ip, fp, fj = horarios
        existente = existentes.get(fecha)
        if existente is None:
            db.add(RegistroDiario(
                empleado_id=empleado.id, fecha=fecha,
                tipo=tipo, fuente=FUENTE_WIZARD, cerrado=True,
                inicio_jornada=ij, inicio_pausa=ip, fin_pausa=fp, fin_jornada=fj,
                observaciones=obs,
            ))
        else:
            existente.tipo = tipo
            existente.fuente = FUENTE_WIZARD
            existente.cerrado = True
            existente.inicio_jornada = ij
            existente.inicio_pausa = ip
            existente.fin_pausa = fp
            existente.fin_jornada = fj
            existente.observaciones = obs

    db.commit()
