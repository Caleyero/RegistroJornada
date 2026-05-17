"""Planificador asistido de turnos.

Tablero semanal por centro: RRHH asigna turnos, el sistema valida
conflictos, calcula la cobertura frente a la dotación y propone
sustitutos. Accesible para RRHH y administradores.
"""

from datetime import date, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import require_rrhh
from app.dependencies import get_db
from app.models import CentroTrabajo, Empleado, PlantillaTurno, TurnoPlanificado, Usuario
from app.models.registro_diario import FUENTE_AUTO, TIPO_TRABAJADO
from app.models.turno_planificado import ESTADO_BORRADOR, ESTADO_PUBLICADO
from app.services import conflictos_service, diario_service, turnos_service
from app.services.diario_service import DiaPayload
from app.templating import render


router = APIRouter(prefix="/planificacion", tags=["planificacion"])


# ---------------------------------------------------------------------------
# Helpers de semana
# ---------------------------------------------------------------------------

def _lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def _parse_lunes(valor: str | None) -> date:
    """Normaliza el parámetro `lunes` al lunes de esa semana (hoy por defecto)."""
    if valor:
        try:
            return _lunes_de(date.fromisoformat(valor))
        except ValueError:
            pass
    return _lunes_de(date.today())


def _get_centro(db: Session, centro_id: int) -> CentroTrabajo:
    centro = db.get(CentroTrabajo, centro_id)
    if centro is None:
        raise HTTPException(status_code=404, detail="Centro no encontrado.")
    return centro


def _volcar_turnos_a_diario(
    db: Session, centro: CentroTrabajo, lunes: date,
) -> dict:
    """Vuelca al RegistroDiario los turnos publicados de la semana.

    Deja un prefill (`fuente=auto`) en el registro horario del empleado, que
    este podrá luego confirmar o ajustar. Es transaccional por día: si un
    turno falla (mes cerrado, fuera de periodo...), los demás continúan.
    """
    domingo = lunes + timedelta(days=6)
    turnos = (
        db.query(TurnoPlanificado)
        .filter(
            TurnoPlanificado.centro_id == centro.id,
            TurnoPlanificado.fecha >= lunes,
            TurnoPlanificado.fecha <= domingo,
            TurnoPlanificado.estado == ESTADO_PUBLICADO,
            TurnoPlanificado.volcado_diario.is_(False),
        )
        .all()
    )
    volcados = 0
    errores: list[str] = []
    for tp in turnos:
        # Un turno sin pausa se vuelca con una pausa de 0 minutos: el
        # RegistroDiario exige los cuatro horarios para un día trabajado.
        ini_pausa = tp.inicio_pausa or tp.hora_inicio
        fin_pausa = tp.fin_pausa or tp.hora_inicio
        payload = DiaPayload(
            tipo=TIPO_TRABAJADO,
            inicio_jornada=tp.hora_inicio, inicio_pausa=ini_pausa,
            fin_pausa=fin_pausa, fin_jornada=tp.hora_fin,
            observaciones=f"Turno planificado · {centro.nombre}",
        )
        try:
            diario_service.upsert_dia(
                db, tp.empleado, tp.fecha, payload, fuente=FUENTE_AUTO,
            )
            tp.volcado_diario = True
            volcados += 1
        except (ValueError, PermissionError) as exc:
            errores.append(
                f"{tp.empleado.nombre_completo} ({tp.fecha:%d/%m}): {exc}"
            )
    db.commit()
    return {"volcados": volcados, "errores": errores}


def _copiar_semana(
    db: Session, centro: CentroTrabajo, origen: date, destino: date,
) -> dict:
    """Duplica los turnos de la semana `origen` en la semana `destino`.

    Cada turno se copia al mismo día de la semana, siempre como borrador.
    Se omite (sin romper) lo que no encaja: empleado que ya tiene turno ese
    día, de vacaciones/baja o fuera de su periodo de alta.
    """
    delta = (destino - origen).days
    fuente = (
        db.query(TurnoPlanificado)
        .filter(
            TurnoPlanificado.centro_id == centro.id,
            TurnoPlanificado.fecha >= origen,
            TurnoPlanificado.fecha <= origen + timedelta(days=6),
        )
        .all()
    )
    copiados = 0
    omitidos: list[str] = []
    for tp in fuente:
        nueva = tp.fecha + timedelta(days=delta)
        emp = tp.empleado
        if conflictos_service.turno_planificado_en(db, tp.empleado_id, nueva):
            omitidos.append(f"{emp.nombre_completo} {nueva:%d/%m}: ya tenía turno")
            continue
        if conflictos_service.periodo_vacaciones_en(db, tp.empleado_id, nueva):
            omitidos.append(f"{emp.nombre_completo} {nueva:%d/%m}: vacaciones/baja")
            continue
        if diario_service.dia_fuera_de_periodo(emp, nueva):
            omitidos.append(f"{emp.nombre_completo} {nueva:%d/%m}: fuera de alta")
            continue
        db.add(TurnoPlanificado(
            fecha=nueva, empleado_id=tp.empleado_id, centro_id=centro.id,
            plantilla_turno_id=tp.plantilla_turno_id,
            hora_inicio=tp.hora_inicio, hora_fin=tp.hora_fin,
            inicio_pausa=tp.inicio_pausa, fin_pausa=tp.fin_pausa,
            estado=ESTADO_BORRADOR,
        ))
        copiados += 1
    db.commit()
    return {"copiados": copiados, "omitidos": omitidos}


# ---------------------------------------------------------------------------
# Selector de centro
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse, name="planificacion_index")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    centros = (
        db.query(CentroTrabajo)
        .filter(CentroTrabajo.activo.is_(True))
        .order_by(CentroTrabajo.nombre)
        .all()
    )
    return render(
        request, db, "planificacion/selector.html",
        current_user=current, centros=centros,
        lunes=_lunes_de(date.today()).isoformat(),
    )


# ---------------------------------------------------------------------------
# Tablero semanal
# ---------------------------------------------------------------------------

@router.get("/{centro_id}", response_class=HTMLResponse, name="planificacion_tablero")
def tablero(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    lunes: str | None = None,
    aviso: str | None = None,
):
    centro = _get_centro(db, centro_id)
    lun = _parse_lunes(lunes)
    dias = [lun + timedelta(days=i) for i in range(7)]
    turnos = turnos_service.turnos_de(db, centro.id, solo_activos=True)

    tps = (
        db.query(TurnoPlanificado)
        .filter(
            TurnoPlanificado.centro_id == centro.id,
            TurnoPlanificado.fecha >= dias[0],
            TurnoPlanificado.fecha <= dias[-1],
        )
        .all()
    )
    asignaciones: dict[str, dict[int, list[TurnoPlanificado]]] = {}
    for tp in tps:
        (asignaciones
            .setdefault(tp.fecha.isoformat(), {})
            .setdefault(tp.plantilla_turno_id, [])
            .append(tp))

    cobertura = {d.isoformat(): conflictos_service.calcular_cobertura(db, centro, d)
                 for d in dias}
    huecos = [
        (d, cob)
        for d in dias
        for cob in cobertura[d.isoformat()].values()
        if cob.semaforo == "rojo"
    ]
    n_borrador = sum(1 for tp in tps if tp.estado == ESTADO_BORRADOR)
    n_volcables = sum(
        1 for tp in tps
        if tp.estado == ESTADO_PUBLICADO and not tp.volcado_diario
    )

    return render(
        request, db, "planificacion/tablero.html",
        current_user=current, centro=centro,
        dias=dias, turnos=turnos,
        asignaciones=asignaciones, cobertura=cobertura,
        dias_nombre=turnos_service.DIAS_SEMANA,
        lunes=lun, hoy=date.today(),
        semana_prev=(lun - timedelta(days=7)).isoformat(),
        semana_sig=(lun + timedelta(days=7)).isoformat(),
        huecos=huecos, n_borrador=n_borrador, n_volcables=n_volcables,
        total_turnos=len(tps), aviso=aviso,
    )


# ---------------------------------------------------------------------------
# Asignar un turno (con buscador de sustitutos)
# ---------------------------------------------------------------------------

def _render_asignar(request, db, current, centro, fecha, turno):
    candidatos = conflictos_service.buscar_sustitutos(db, centro, fecha, turno)
    cobertura = conflictos_service.calcular_cobertura(db, centro, fecha)
    lun = _lunes_de(fecha)
    return render(
        request, db, "planificacion/asignar.html",
        current_user=current, centro=centro, fecha=fecha, turno=turno,
        candidatos=candidatos, cobertura=cobertura.get(turno.id),
        dia_nombre=turnos_service.DIAS_SEMANA[fecha.weekday()],
        lunes=lun.isoformat(),
        semana=[lun + timedelta(days=i) for i in range(7)],
        dia_base=fecha.weekday(),
    )


@router.get("/{centro_id}/asignar", response_class=HTMLResponse, name="planificacion_asignar_form")
def asignar_form(
    centro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    fecha: str = "",
    plantilla_turno_id: int = 0,
):
    centro = _get_centro(db, centro_id)
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha no válida.")
    turno = db.get(PlantillaTurno, plantilla_turno_id)
    if turno is None or turno.centro_id != centro.id:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    return _render_asignar(request, db, current, centro, f, turno)


@router.post("/{centro_id}/asignar", name="planificacion_asignar")
def asignar(
    centro_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    empleado_id: int = Form(...),
    fecha: str = Form(...),
    plantilla_turno_id: int = Form(...),
    dias: list[int] = Form(default=[]),
):
    """Asigna un empleado a un turno en el día elegido y, opcionalmente, en
    otros días de la misma semana de una sola vez (mejor esfuerzo: omite los
    días con conflicto bloqueante y los informa)."""
    centro = _get_centro(db, centro_id)
    try:
        base = date.fromisoformat(fecha)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fecha no válida.")
    turno = db.get(PlantillaTurno, plantilla_turno_id)
    if turno is None or turno.centro_id != centro.id:
        raise HTTPException(status_code=404, detail="Turno no encontrado.")
    empleado = db.get(Empleado, empleado_id)
    if empleado is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado.")

    lun = _lunes_de(base)
    objetivo = {base}
    for d in dias:
        if 0 <= d <= 6:
            objetivo.add(lun + timedelta(days=d))

    asignados = 0
    omitidos: list[str] = []
    for f in sorted(objetivo):
        conflictos = conflictos_service.validar_asignacion(
            db, empleado, f, turno, centro,
        )
        bloqueantes = [c for c in conflictos if c.es_bloqueante]
        if bloqueantes:
            omitidos.append(f"{f:%d/%m} ({bloqueantes[0].mensaje})")
            continue
        db.add(TurnoPlanificado(
            fecha=f, empleado_id=empleado.id, centro_id=centro.id,
            plantilla_turno_id=turno.id,
            hora_inicio=turno.hora_inicio, hora_fin=turno.hora_fin,
            inicio_pausa=turno.inicio_pausa, fin_pausa=turno.fin_pausa,
            estado=ESTADO_BORRADOR,
        ))
        asignados += 1
    db.commit()

    aviso = f"{empleado.nombre_completo}: {asignados} turno(s) asignado(s)."
    if omitidos:
        aviso += " Omitidos — " + " · ".join(omitidos)
    params = urlencode({"lunes": lun.isoformat(), "aviso": aviso})
    return RedirectResponse(f"/planificacion/{centro.id}?{params}", status_code=303)


@router.post("/turno/{turno_id}/eliminar", name="planificacion_turno_eliminar")
def turno_eliminar(
    turno_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
):
    tp = db.get(TurnoPlanificado, turno_id)
    if tp is None:
        raise HTTPException(status_code=404, detail="Turno planificado no encontrado.")
    centro_id = tp.centro_id
    lunes = _lunes_de(tp.fecha).isoformat()
    db.delete(tp)
    db.commit()
    return RedirectResponse(
        f"/planificacion/{centro_id}?lunes={lunes}", status_code=303,
    )


@router.post("/{centro_id}/publicar", name="planificacion_publicar")
def publicar(
    centro_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    lunes: str = Form(...),
):
    centro = _get_centro(db, centro_id)
    lun = _parse_lunes(lunes)
    (db.query(TurnoPlanificado)
        .filter(
            TurnoPlanificado.centro_id == centro.id,
            TurnoPlanificado.fecha >= lun,
            TurnoPlanificado.fecha <= lun + timedelta(days=6),
            TurnoPlanificado.estado == ESTADO_BORRADOR,
        )
        .update({TurnoPlanificado.estado: ESTADO_PUBLICADO},
                synchronize_session=False))
    db.commit()
    return RedirectResponse(
        f"/planificacion/{centro.id}?lunes={lun.isoformat()}", status_code=303,
    )


@router.post("/{centro_id}/copiar-semana", name="planificacion_copiar_semana")
def copiar_semana(
    centro_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    lunes: str = Form(...),
):
    centro = _get_centro(db, centro_id)
    destino = _parse_lunes(lunes)
    origen = destino - timedelta(days=7)
    r = _copiar_semana(db, centro, origen, destino)
    if not r["copiados"] and not r["omitidos"]:
        aviso = "La semana anterior no tiene turnos planificados que copiar."
    else:
        aviso = f"{r['copiados']} turno(s) copiado(s) de la semana anterior."
        if r["omitidos"]:
            detalle = " · ".join(r["omitidos"][:4])
            aviso += f" {len(r['omitidos'])} omitido(s): {detalle}"
    params = urlencode({"lunes": destino.isoformat(), "aviso": aviso})
    return RedirectResponse(
        f"/planificacion/{centro.id}?{params}", status_code=303,
    )


@router.post("/{centro_id}/volcar", name="planificacion_volcar")
def volcar(
    centro_id: int,
    db: Session = Depends(get_db),
    current: Usuario = Depends(require_rrhh),
    lunes: str = Form(...),
):
    centro = _get_centro(db, centro_id)
    lun = _parse_lunes(lunes)
    resultado = _volcar_turnos_a_diario(db, centro, lun)
    if not resultado["volcados"] and not resultado["errores"]:
        aviso = "No había turnos publicados pendientes de volcar."
    else:
        aviso = (
            f"{resultado['volcados']} turno(s) volcado(s) al registro diario."
        )
        if resultado["errores"]:
            detalle = " / ".join(resultado["errores"][:3])
            aviso += f" {len(resultado['errores'])} con error: {detalle}"
    params = urlencode({"lunes": lun.isoformat(), "aviso": aviso})
    return RedirectResponse(
        f"/planificacion/{centro.id}?{params}", status_code=303,
    )
