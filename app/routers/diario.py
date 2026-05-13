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

    dias = diario_service.asegurar_mes(db, empleado, anio, mes)
    cerrado = diario_service.mes_esta_cerrado(dias)
    horario_tipo = diario_service.horario_tipo_de_empleado(empleado)
    dias_laborables_habit = set(diario_service.dias_laborables_de_empleado(empleado))
    pendientes_pasados = diario_service.pendientes_laborables_pasados(
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
            fila.append({
                "fecha": fecha, "en_mes": True, "dia": dia,
                "pendiente": dia is None,
                "pendiente_pasado": fecha in set_pendientes_pasados,
                "es_hoy": fecha == hoy,
                "es_festivo_calendario": es_festivo_calendario,
                "dow_laborable": fecha.weekday() in dias_laborables_habit,
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
        suffix=suffix,
        horas_str=horas_str,
        dias_trabajados=dias_trabajados,
        pendientes_pasados=pendientes_pasados,
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

    # Garantiza la fila (si es un día pasado sin auto-rellenar todavía).
    diario_service.asegurar_mes(db, empleado, anio, mes)

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
    suffix = f"?empleado_id={empleado.id}" if current.es_admin else ""

    return render(
        request, db, "diario/editar_dia.html",
        current_user=current,
        empleado=empleado, fecha=fecha, anio=anio, mes=mes, dia=dia,
        registro=registro, horario_tipo=horario_tipo, suffix=suffix,
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

    dias = diario_service.asegurar_mes(db, empleado, anio, mes)
    if not dias:
        raise HTTPException(
            status_code=400,
            detail="No hay días registrados para este mes; no se puede generar el PDF.",
        )

    pendientes = diario_service.pendientes_laborables_pasados(
        empleado, anio, mes, dias,
    )
    if pendientes:
        fechas = ", ".join(p.isoformat() for p in pendientes[:5])
        extra = f" (+{len(pendientes) - 5} más)" if len(pendientes) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=(
                f"No se puede cerrar el mes: hay {len(pendientes)} día(s) "
                f"laborable(s) sin confirmar: {fechas}{extra}. Abre cada uno "
                "en el calendario y confírmalo antes de generar el PDF mensual."
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
