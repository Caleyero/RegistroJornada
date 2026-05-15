"""Registro diario de jornada (art. 34.9 ET).

Vista principal del empleado tras el login: calendario mensual con auto-relleno
según el horario habitual y los festivos del Principado de Asturias. Edición
día a día con prevalencia sobre el horario tipo. Al "cerrar el mes" se genera
el PDF mensual firmable a partir de los días confirmados.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_login
from app.dependencies import get_db
from app.models import Empleado, Usuario
from app.routers.registros import (
    RegistroPayload, _generar_pdf_desde_registro, _nombre_pdf, _upsert_registro,
)
from app.services import diario_service
from app.services.diario_service import DiaPayload
from app.services.festivos import FESTIVOS_ASTURIAS
from app.templating import render


router = APIRouter(
    prefix="/diario",
    tags=["diario"],
    dependencies=[Depends(require_login)],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolver_empleado(
    db: Session, current: Usuario, empleado_id: int | None,
) -> Empleado:
    """Devuelve el empleado sobre el que se opera.

    - Usuario normal: siempre el suyo. `empleado_id` se ignora salvo que
      coincida con el propio (mismo principio que en registros.py).
    - Admin: usa `empleado_id` si viene; si no, aborta con 400 para forzar
      la selección desde la UI.
    """
    if not current.es_admin:
        if current.empleado_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Tu usuario no está vinculado a ningún empleado. "
                    "Pídele al administrador que te vincule en /admin/usuarios."
                ),
            )
        if empleado_id is not None and empleado_id != current.empleado_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No puedes acceder al registro diario de otro empleado.",
            )
        empleado = db.get(Empleado, current.empleado_id)
        if empleado is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El empleado vinculado a tu usuario ya no existe.",
            )
        return empleado

    if empleado_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selecciona un empleado en la lista (?empleado_id=).",
        )
    empleado = db.get(Empleado, empleado_id)
    if empleado is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")
    return empleado


def _mes_navegacion(anio: int, mes: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Devuelve ((anio_prev, mes_prev), (anio_sig, mes_sig))."""
    prev = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    sig = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return prev, sig


def _validar_mes(anio: int, mes: int) -> None:
    if not (2020 <= anio <= 2099) or not (1 <= mes <= 12):
        raise HTTPException(status_code=400, detail="Mes/año fuera de rango.")


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, name="diario_home")
def diario_home(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = None,
):
    """Aterrizaje del empleado: redirige a su calendario del mes en curso.

    Para admins sin `empleado_id`, muestra un selector con todos los empleados.
    """
    hoy = date.today()
    if current.es_admin and empleado_id is None:
        empleados = (
            db.query(Empleado)
            .filter(Empleado.activo == True)  # noqa: E712
            .order_by(Empleado.apellidos, Empleado.nombre)
            .all()
        )
        return render(
            request, db, "diario/selector_empleado.html",
            empleados=empleados, anio=hoy.year, mes=hoy.month,
        )

    empleado = _resolver_empleado(db, current, empleado_id)
    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""
    return RedirectResponse(
        f"/diario/{hoy.year}/{hoy.month:02d}{suffix}", status_code=303,
    )


@router.get("/{anio}/{mes}", response_class=HTMLResponse, name="diario_calendario")
def calendario(
    anio: int,
    mes: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = None,
):
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)

    dias = diario_service.cargar_mes(db, empleado, anio, mes)
    cerrado = diario_service.mes_esta_cerrado(dias)
    horario_tipo = diario_service.horario_tipo_de_empleado(empleado)
    dias_laborables_habit = set(diario_service.dias_laborables_de_empleado(empleado))
    pendientes_pasados = diario_service.pendientes_laborables_pasados(
        empleado, anio, mes, dias,
    )
    pendientes_cierre = diario_service.pendientes_laborables_para_cierre(
        empleado, anio, mes, dias,
    )
    set_pendientes_pasados = set(pendientes_pasados)
    hoy = date.today()

    # Mapa {fecha: dia} para que el template lo consulte fácil.
    dias_por_fecha = {d.fecha: d for d in dias}

    # Construir las "semanas" del mes para el grid 7-col (lun..dom).
    import calendar as _cal
    cal = _cal.Calendar(firstweekday=0)
    semanas: list[list[dict]] = []
    for semana in cal.monthdatescalendar(anio, mes):
        fila: list[dict] = []
        for fecha in semana:
            if fecha.month != mes:
                fila.append({"fecha": fecha, "en_mes": False})
                continue
            dia = dias_por_fecha.get(fecha)
            es_festivo_calendario = fecha.isoformat() in FESTIVOS_ASTURIAS
            fuera_periodo = diario_service.dia_fuera_de_periodo(empleado, fecha)
            es_dow_laborable = fecha.weekday() in dias_laborables_habit
            # Estado visual del día (5 estados mutuamente excluyentes):
            #  - fuera_periodo: anterior a alta / posterior a baja
            #  - confirmado: hay fila en BD (acto del usuario)
            #  - inferido_festivo: festivo del calendario sin fila
            #  - inferido_descanso: DOW no laborable sin fila
            #  - por_confirmar: día laborable sin fila, hoy o pasado
            #  - pendiente: día laborable sin fila, futuro
            if fuera_periodo:
                estado = "fuera_periodo"
            elif dia is not None:
                estado = "confirmado"
            elif es_festivo_calendario:
                estado = "inferido_festivo"
            elif not es_dow_laborable:
                estado = "inferido_descanso"
            elif fecha <= hoy:
                estado = "por_confirmar"
            else:
                estado = "pendiente"
            fila.append({
                "fecha": fecha, "en_mes": True, "dia": dia,
                "estado": estado,
                "pendiente_pasado": fecha in set_pendientes_pasados,
                "es_hoy": fecha == hoy,
                "es_festivo_calendario": es_festivo_calendario,
                "festivo_desc": FESTIVOS_ASTURIAS.get(fecha.isoformat(), ""),
                "dow_laborable": es_dow_laborable,
                "fuera_periodo": fuera_periodo,
                "clickable": not fuera_periodo,
            })
        semanas.append(fila)

    # Resumen de horas (sólo días trabajados).
    minutos_trabajados = 0
    dias_trabajados = 0
    for d in dias:
        if d.tipo != "trabajado" or not (
            d.inicio_jornada and d.inicio_pausa and d.fin_pausa and d.fin_jornada
        ):
            continue
        m = (
            diario_service._to_minutos(d.inicio_pausa)
            - diario_service._to_minutos(d.inicio_jornada)
            + diario_service._to_minutos(d.fin_jornada)
            - diario_service._to_minutos(d.fin_pausa)
        )
        if m > 0:
            minutos_trabajados += m
            dias_trabajados += 1
    horas_str = f"{minutos_trabajados // 60}h {minutos_trabajados % 60:02d}m"

    prev, sig = _mes_navegacion(anio, mes)
    # Deshabilitar navegación cuando el mes destino caería entero fuera del
    # periodo de alta/baja del empleado.
    import calendar as _cal2
    def _mes_entero_fuera(a: int, m: int) -> bool:
        ini = date(a, m, 1)
        fin = date(a, m, _cal2.monthrange(a, m)[1])
        if empleado.fecha_alta and fin < empleado.fecha_alta:
            return True
        if empleado.fecha_baja and ini > empleado.fecha_baja:
            return True
        return False
    prev_disabled = _mes_entero_fuera(prev[0], prev[1])
    sig_disabled = _mes_entero_fuera(sig[0], sig[1])

    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""
    return render(
        request, db, "diario/calendario.html",
        current_user=current,
        empleado=empleado,
        anio=anio, mes=mes, semanas=semanas, dias=dias,
        cerrado=cerrado,
        horario_tipo=horario_tipo,
        prev_anio=prev[0], prev_mes=prev[1],
        sig_anio=sig[0], sig_mes=sig[1],
        prev_disabled=prev_disabled, sig_disabled=sig_disabled,
        suffix=suffix,
        horas_str=horas_str,
        dias_trabajados=dias_trabajados,
        pendientes_pasados=pendientes_pasados,
        pendientes_cierre=pendientes_cierre,
    )


@router.get(
    "/{anio}/{mes}/{dia}/editar",
    response_class=HTMLResponse, name="diario_editar",
)
def editar_dia(
    anio: int,
    mes: int,
    dia: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = None,
):
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)
    try:
        fecha = date(anio, mes, dia)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida.")

    if diario_service.dia_fuera_de_periodo(empleado, fecha):
        alta = empleado.fecha_alta.strftime("%d/%m/%Y") if empleado.fecha_alta else "—"
        baja = empleado.fecha_baja.strftime("%d/%m/%Y") if empleado.fecha_baja else "—"
        raise HTTPException(
            status_code=400,
            detail=(
                f"La fecha {fecha.strftime('%d/%m/%Y')} está fuera del periodo "
                f"del empleado (alta {alta}, baja {baja})."
            ),
        )

    from app.models import RegistroDiario
    registro = (
        db.query(RegistroDiario)
        .filter(
            RegistroDiario.empleado_id == empleado.id,
            RegistroDiario.fecha == fecha,
        )
        .first()
    )
    horario_tipo = diario_service.horario_tipo_de_empleado(empleado)
    es_festivo_cal = fecha.isoformat() in FESTIVOS_ASTURIAS
    festivo_desc = FESTIVOS_ASTURIAS.get(fecha.isoformat(), "")
    dow_laborable = fecha.weekday() in set(
        diario_service.dias_laborables_de_empleado(empleado)
    )
    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""

    return render(
        request, db, "diario/editar_dia.html",
        current_user=current,
        empleado=empleado, fecha=fecha, anio=anio, mes=mes, dia=dia,
        registro=registro, horario_tipo=horario_tipo, suffix=suffix,
        es_festivo_cal=es_festivo_cal, festivo_desc=festivo_desc,
        dow_laborable=dow_laborable,
    )


# OJO — orden de declaración: las rutas con segmento literal ("cerrar", "reabrir")
# deben declararse ANTES que las que usan `{dia}` (parámetro tipado int) para
# que Starlette no responda 422 al recibir un literal donde espera un int.

@router.post("/{anio}/{mes}/cerrar", name="diario_cerrar")
def cerrar_y_generar(
    anio: int,
    mes: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = Form(default=None),
):
    """Genera el PDF mensual desde los días, lo guarda como `Registro` y cierra el mes."""
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)

    dias = diario_service.cargar_mes(db, empleado, anio, mes)

    pendientes = diario_service.pendientes_laborables_para_cierre(
        empleado, anio, mes, dias,
    )
    if pendientes:
        fechas = ", ".join(p.strftime("%d/%m/%Y") for p in pendientes[:5])
        extra = f" (+{len(pendientes) - 5} más)" if len(pendientes) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=(
                f"No se puede cerrar el mes: hay {len(pendientes)} día(s) "
                f"laborable(s) sin confirmar: {fechas}{extra}. Abre cada uno "
                "en el calendario y confírmalo antes de generar el PDF mensual. "
                "El mes solo puede cerrarse a medias si el empleado ha cesado "
                "(con fecha de baja dentro del mes)."
            ),
        )

    payload_dict = diario_service.dias_a_payload_pdf(empleado, anio, mes, dias)
    payload = RegistroPayload(**payload_dict)
    registro = _upsert_registro(db, payload)
    pdf_bytes = _generar_pdf_desde_registro(registro)

    diario_service.cerrar_mes(db, empleado, anio, mes)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{_nombre_pdf(registro)}"',
        },
    )


@router.post("/{anio}/{mes}/reabrir", name="diario_reabrir")
def reabrir(
    anio: int,
    mes: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = Form(default=None),
):
    if not current.es_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un administrador puede reabrir un mes cerrado.",
        )
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)
    diario_service.reabrir_mes(db, empleado, anio, mes)
    return RedirectResponse(
        f"/diario/{anio}/{mes:02d}?empleado_id={empleado.id}", status_code=303,
    )


@router.post("/{anio}/{mes}/bulk", name="diario_bulk")
def guardar_bulk(
    anio: int,
    mes: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = Form(default=None),
    fechas: list[str] = Form(...),
    tipo: str = Form(...),
    inicio_jornada: str = Form(""),
    inicio_pausa: str = Form(""),
    fin_pausa: str = Form(""),
    fin_jornada: str = Form(""),
    observaciones: str = Form(""),
):
    """Aplica el mismo tipo/horario a un conjunto de fechas (selección múltiple).

    Las fechas deben venir en formato ISO `YYYY-MM-DD`. Se ignoran las que no
    pertenezcan al mes/año del path.
    """
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)

    fechas_validas: list[date] = []
    fechas_descartadas: list[str] = []
    for iso in fechas:
        try:
            f = date.fromisoformat(iso)
        except ValueError:
            fechas_descartadas.append(iso)
            continue
        if f.year != anio or f.month != mes:
            fechas_descartadas.append(iso)
            continue
        fechas_validas.append(f)

    if not fechas_validas:
        raise HTTPException(
            status_code=400,
            detail="No se ha recibido ninguna fecha válida en la selección.",
        )

    payload = DiaPayload(
        tipo=tipo,
        inicio_jornada=inicio_jornada or None,
        inicio_pausa=inicio_pausa or None,
        fin_pausa=fin_pausa or None,
        fin_jornada=fin_jornada or None,
        observaciones=observaciones,
    )

    resultado = diario_service.upsert_dias_bulk(db, empleado, fechas_validas, payload)

    if resultado["errores"]:
        # Aplicamos lo que se haya podido y devolvemos detalle de errores.
        errs = "; ".join(f"{f}: {m}" for f, m in resultado["errores"][:5])
        extra = f" (+{len(resultado['errores'])-5} más)" if len(resultado["errores"]) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=(
                f"Aplicados {resultado['aplicados']} de {len(fechas_validas)}. "
                f"Errores: {errs}{extra}"
            ),
        )

    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""
    return RedirectResponse(f"/diario/{anio}/{mes:02d}{suffix}", status_code=303)


@router.post("/{anio}/{mes}/bulk-revertir", name="diario_bulk_revertir")
def revertir_bulk(
    anio: int,
    mes: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = Form(default=None),
    fechas: list[str] = Form(...),
):
    """Borra los `RegistroDiario` de un conjunto de fechas → vuelven a pendiente."""
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)

    fechas_validas: list[date] = []
    for iso in fechas:
        try:
            f = date.fromisoformat(iso)
        except ValueError:
            continue
        if f.year == anio and f.month == mes:
            fechas_validas.append(f)
    if not fechas_validas:
        raise HTTPException(
            status_code=400, detail="Ninguna fecha válida en la selección.",
        )

    resultado = diario_service.borrar_dias_bulk(db, empleado, fechas_validas)
    if resultado["errores"]:
        errs = "; ".join(f"{f}: {m}" for f, m in resultado["errores"][:5])
        extra = f" (+{len(resultado['errores'])-5} más)" if len(resultado["errores"]) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=(
                f"Revertidos {resultado['borrados']} de {len(fechas_validas)}. "
                f"Errores: {errs}{extra}"
            ),
        )

    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""
    return RedirectResponse(f"/diario/{anio}/{mes:02d}{suffix}", status_code=303)


@router.post("/{anio}/{mes}/{dia}/borrar", name="diario_borrar_dia")
def borrar_un_dia(
    anio: int,
    mes: int,
    dia: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = Form(default=None),
):
    """Revierte un día concreto a pendiente borrando su `RegistroDiario`."""
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)
    try:
        fecha = date(anio, mes, dia)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida.")
    try:
        diario_service.borrar_dia(db, empleado, fecha)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""
    return RedirectResponse(f"/diario/{anio}/{mes:02d}{suffix}", status_code=303)


@router.post("/{anio}/{mes}/{dia}", name="diario_guardar")
def guardar_dia(
    anio: int,
    mes: int,
    dia: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_login),
    empleado_id: int | None = Form(default=None),
    tipo: str = Form(...),
    inicio_jornada: str = Form(""),
    inicio_pausa: str = Form(""),
    fin_pausa: str = Form(""),
    fin_jornada: str = Form(""),
    observaciones: str = Form(""),
):
    _validar_mes(anio, mes)
    empleado = _resolver_empleado(db, current, empleado_id)
    try:
        fecha = date(anio, mes, dia)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha inválida.")

    payload = DiaPayload(
        tipo=tipo,
        inicio_jornada=inicio_jornada or None,
        inicio_pausa=inicio_pausa or None,
        fin_pausa=fin_pausa or None,
        fin_jornada=fin_jornada or None,
        observaciones=observaciones,
    )

    try:
        diario_service.upsert_dia(db, empleado, fecha, payload)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""
    return RedirectResponse(f"/diario/{anio}/{mes:02d}{suffix}", status_code=303)
