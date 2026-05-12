"""Generación del PDF mensual de registro de jornada.

Diseño minimalista en escala de grises, monoespaciado (Consolas),
basado en el modelo "Registro Diario de Jornada · Ej. AAAA / MES".
"""

import calendar
from datetime import date
from pathlib import Path

from fpdf import FPDF


_FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_CONSOLAS_REGULAR = _FONTS_DIR / "consola.ttf"
_CONSOLAS_BOLD = _FONTS_DIR / "consolab.ttf"
_CONSOLAS_ITALIC = _FONTS_DIR / "consolai.ttf"
FONT_NAME = "Consolas"


DIAS_SEMANA = [
    "lunes", "martes", "miércoles", "jueves",
    "viernes", "sábado", "domingo",
]

MESES_NOMBRE = [
    "", "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]


# Paleta — sólo escala de grises
COLOR_DARK = (45, 45, 45)            # cabeceras de sección (texto blanco encima)
COLOR_LIGHT = (232, 232, 232)        # etiquetas y cabeceras de tabla
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)


def _registrar_fuentes(pdf: FPDF) -> str:
    if _CONSOLAS_REGULAR.exists():
        pdf.add_font(FONT_NAME, "", str(_CONSOLAS_REGULAR))
        pdf.add_font(FONT_NAME, "B", str(_CONSOLAS_BOLD))
        pdf.add_font(FONT_NAME, "I", str(_CONSOLAS_ITALIC))
        return FONT_NAME
    return "Courier"


def _to_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _minutos_a_hhmm(minutos: int) -> str:
    h, m = divmod(max(0, minutos), 60)
    return f"{h}:{m:02d}"


def _calcular_minutos_jornada(
    inicio_jornada: str, inicio_pausa: str, fin_pausa: str, fin_jornada: str,
) -> int:
    bloque_manana = _to_minutos(inicio_pausa) - _to_minutos(inicio_jornada)
    bloque_tarde = _to_minutos(fin_jornada) - _to_minutos(fin_pausa)
    return max(0, bloque_manana) + max(0, bloque_tarde)


def generar_pdf_registro_mensual(
    *,
    empresa_nombre: str,
    empresa_cif: str,
    empresa_ccc: str,
    empleado_nombre: str,
    empleado_apellidos: str,
    empleado_nif: str,
    empleado_naf: str,
    anio: int,
    mes: int,
    dias_laborables: list[int],
    inicio_jornada: str,
    inicio_pausa: str,
    fin_pausa: str,
    fin_jornada: str,
    festivos: dict[str, str],
    vacaciones: set[str] | list[str],
    ausencias: dict[str, str] | None = None,
    overrides_horario: dict[str, dict[str, str]] | None = None,
) -> bytes:
    """Devuelve el PDF (bytes) del registro mensual."""
    ausencias = ausencias or {}
    overrides_horario = overrides_horario or {}
    if isinstance(vacaciones, list):
        vacaciones = set(vacaciones)

    minutos_dia_global = _calcular_minutos_jornada(
        inicio_jornada, inicio_pausa, fin_pausa, fin_jornada,
    )
    _, dias_en_mes = calendar.monthrange(anio, mes)
    hay_overrides = False  # se vuelve True si algún día imprime override

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)
    LEFT, TOP, RIGHT = 15, 12, 15
    pdf.set_margins(LEFT, TOP, RIGHT)
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)

    fnt = _registrar_fuentes(pdf)

    PAGE_W = 210
    CONTENT_W = PAGE_W - LEFT - RIGHT  # 180 mm

    # =====================================================================
    # 1. Banda superior: "REGISTRO DIARIO DE JORNADA"  |  "Ej. AAAA / MES"
    # =====================================================================
    pdf.set_fill_color(*COLOR_DARK)
    pdf.set_text_color(*COLOR_WHITE)
    pdf.set_font(fnt, "B", 10)

    w_title = CONTENT_W * 0.62
    w_period = CONTENT_W - w_title
    pdf.cell(w_title, 7, " REGISTRO DIARIO DE JORNADA", border=1, fill=True, align="L")
    pdf.cell(w_period, 7, f"Ej. {anio} / {MESES_NOMBRE[mes]} ",
             border=1, fill=True, align="R")
    pdf.ln(7)

    # =====================================================================
    # 2. Cabecera EMPRESA / TRABAJADOR (4 filas)
    # =====================================================================
    pdf.set_text_color(*COLOR_BLACK)
    row_h_head = 6
    label_w = 30                                      # ancho columna etiqueta
    val_w_split = (CONTENT_W - 2 * label_w) / 2       # ancho de cada valor en filas con 4 cols

    def _label_cell(text: str, w: float = label_w) -> None:
        pdf.set_fill_color(*COLOR_LIGHT)
        pdf.set_text_color(*COLOR_BLACK)
        pdf.set_font(fnt, "", 8)
        pdf.cell(w, row_h_head, " " + text, border=1, fill=True, align="L")

    def _value_cell(text: str, w: float) -> None:
        pdf.set_fill_color(*COLOR_WHITE)
        pdf.set_text_color(*COLOR_BLACK)
        pdf.set_font(fnt, "B", 9)
        pdf.cell(w, row_h_head, " " + text, border=1, fill=False, align="L")

    # Fila 1: EMPRESA | nombre (ocupa el resto)
    _label_cell("EMPRESA")
    _value_cell(empresa_nombre or "", CONTENT_W - label_w)
    pdf.ln(row_h_head)

    # Fila 2: CIF | val | C.C.C. | val
    _label_cell("CIF")
    _value_cell(empresa_cif or "", val_w_split)
    _label_cell("C.C.C.")
    _value_cell(empresa_ccc or "", val_w_split)
    pdf.ln(row_h_head)

    # Fila 3: TRABAJADOR | nombre completo
    _label_cell("TRABAJADOR")
    trabajador_full = f"{empleado_nombre} {empleado_apellidos}".strip().upper()
    _value_cell(trabajador_full, CONTENT_W - label_w)
    pdf.ln(row_h_head)

    # Fila 4: NIF | val | NAF | val
    _label_cell("NIF")
    _value_cell((empleado_nif or "").upper(), val_w_split)
    _label_cell("NAF")
    _value_cell(empleado_naf or "", val_w_split)
    pdf.ln(row_h_head)

    pdf.ln(2)

    # =====================================================================
    # 3. Banda "JORNADAS DIARIAS"
    # =====================================================================
    pdf.set_fill_color(*COLOR_DARK)
    pdf.set_text_color(*COLOR_WHITE)
    pdf.set_font(fnt, "B", 9)
    pdf.cell(CONTENT_W, 6, " JORNADAS DIARIAS", border=1, fill=True, align="L")
    pdf.ln(6)

    # =====================================================================
    # 4. Cabecera de columnas
    # =====================================================================
    cols_w = [10, 24, 18, 18, 18, 18, 16, 58]   # suma = 180 mm
    assert abs(sum(cols_w) - CONTENT_W) < 0.01

    headers = ["D", "SEMANA", "INICIO", "I·PAUSA", "F·PAUSA", "FIN", "H", "OBSERVACIONES"]
    aligns_h = ["C",  "L",      "C",      "C",       "C",       "C",   "C", "L"]

    pdf.set_fill_color(*COLOR_LIGHT)
    pdf.set_text_color(*COLOR_BLACK)
    pdf.set_font(fnt, "B", 8)
    for i, h in enumerate(headers):
        txt = h if aligns_h[i] != "L" else " " + h
        pdf.cell(cols_w[i], 6, txt, border=1, fill=True, align=aligns_h[i])
    pdf.ln(6)

    # =====================================================================
    # 5. Filas día a día
    # =====================================================================
    row_h = 5.5
    minutos_totales = 0

    for dia_num in range(1, dias_en_mes + 1):
        fecha_dia = date(anio, mes, dia_num)
        weekday = fecha_dia.weekday()
        fecha_iso = fecha_dia.isoformat()

        es_laborable = weekday in dias_laborables
        es_festivo = fecha_iso in festivos
        es_vacaciones = fecha_iso in vacaciones
        es_ausencia = fecha_iso in ausencias
        pintar_horario = (es_laborable and not es_festivo
                          and not es_vacaciones and not es_ausencia)

        if es_festivo:
            observ = f"FESTIVO · {festivos[fecha_iso]}" if festivos[fecha_iso] else "FESTIVO"
        elif es_vacaciones:
            observ = "VACACIONES"
        elif es_ausencia:
            motivo = ausencias[fecha_iso]
            observ = f"AUSENCIA JUSTIFICADA · {motivo}" if motivo else "AUSENCIA JUSTIFICADA"
        else:
            observ = ""

        # Columna D — número de día (negrita)
        pdf.set_fill_color(*COLOR_WHITE)
        pdf.set_text_color(*COLOR_BLACK)
        pdf.set_font(fnt, "B", 8)
        pdf.cell(cols_w[0], row_h, str(dia_num), border=1, align="C")

        # Columna SEMANA — minúsculas, alineado izda con padding
        pdf.set_font(fnt, "", 8)
        pdf.cell(cols_w[1], row_h, " " + DIAS_SEMANA[weekday], border=1, align="L")

        if pintar_horario:
            ov = overrides_horario.get(fecha_iso)
            if ov:
                ij = ov.get("inicio_jornada", inicio_jornada)
                ip = ov.get("inicio_pausa",   inicio_pausa)
                fp = ov.get("fin_pausa",      fin_pausa)
                fj = ov.get("fin_jornada",    fin_jornada)
                minutos_hoy = _calcular_minutos_jornada(ij, ip, fp, fj)
                hay_overrides = True
            else:
                ij, ip, fp, fj = inicio_jornada, inicio_pausa, fin_pausa, fin_jornada
                minutos_hoy = minutos_dia_global

            pdf.cell(cols_w[2], row_h, ij, border=1, align="C")
            pdf.cell(cols_w[3], row_h, ip, border=1, align="C")
            pdf.cell(cols_w[4], row_h, fp, border=1, align="C")
            pdf.cell(cols_w[5], row_h, fj, border=1, align="C")
            pdf.set_font(fnt, "B", 8)
            horas_txt = _minutos_a_hhmm(minutos_hoy) + ("*" if ov else "")
            pdf.cell(cols_w[6], row_h, horas_txt, border=1, align="C")
            pdf.set_font(fnt, "", 8)
            minutos_totales += minutos_hoy
        else:
            for w in cols_w[2:7]:
                pdf.cell(w, row_h, "", border=1)

        # Columna OBSERVACIONES
        pdf.cell(cols_w[7], row_h, " " + observ, border=1, align="L")
        pdf.ln(row_h)

    # =====================================================================
    # 6. Fila HORAS TOTALES DEL PERIODO
    # =====================================================================
    pdf.set_fill_color(*COLOR_LIGHT)
    pdf.set_text_color(*COLOR_BLACK)
    pdf.set_font(fnt, "B", 8)
    pdf.cell(sum(cols_w[:6]), 6, "HORAS TOTALES DEL PERIODO ",
             border=1, fill=True, align="R")
    horas_tot = minutos_totales // 60
    mins_tot = minutos_totales % 60
    pdf.set_fill_color(*COLOR_WHITE)
    pdf.cell(cols_w[6], 6, f"{horas_tot}:{mins_tot:02d}:00",
             border=1, fill=False, align="C")
    pdf.cell(cols_w[7], 6, "", border=1)
    pdf.ln(6)

    # =====================================================================
    # 7. Pie de tabla (nota aclaratoria)
    # =====================================================================
    pdf.ln(2)
    pdf.set_font(fnt, "", 7)
    pdf.set_text_color(*COLOR_BLACK)
    pdf.cell(CONTENT_W, 4,
             "* Consignar en OBSERVACIONES: FESTIVO · VACACIONES · "
             "AUSENCIA JUSTIFICADA cuando proceda.",
             border=0, align="L")
    if hay_overrides:
        pdf.ln(4)
        pdf.cell(CONTENT_W, 4,
                 "* En la columna H, el asterisco indica HORARIO PROPIO de ese día.",
                 border=0, align="L")

    # =====================================================================
    # 8. Bloque de firmas (fijo en la parte inferior)
    # =====================================================================
    SIG_BLOCK_H = 28
    BOTTOM_MARGIN = 15
    y_sig = 297 - BOTTOM_MARGIN - SIG_BLOCK_H

    gap = 6
    box_w = (CONTENT_W - gap) / 2
    x_left = LEFT
    x_right = LEFT + box_w + gap

    # Cabecera "FIRMA DEL TRABAJADOR" / "FIRMA Y SELLO DE LA EMPRESA"
    pdf.set_xy(x_left, y_sig)
    pdf.set_fill_color(*COLOR_LIGHT)
    pdf.set_font(fnt, "B", 8)
    pdf.cell(box_w, 5, " FIRMA DEL TRABAJADOR", border=1, fill=True, align="L")
    pdf.set_xy(x_right, y_sig)
    pdf.cell(box_w, 5, " FIRMA Y SELLO DE LA EMPRESA", border=1, fill=True, align="L")

    # Línea de guiones justo debajo (zona de firma)
    pdf.set_font(fnt, "", 8)
    char_w = pdf.get_string_width("-")
    n_dashes = max(1, int((box_w - 1) / char_w))
    dashes = "-" * n_dashes

    pdf.set_xy(x_left, y_sig + 5)
    pdf.cell(box_w, 5, dashes, border=0, align="L")
    pdf.set_xy(x_right, y_sig + 5)
    pdf.cell(box_w, 5, dashes, border=0, align="L")

    # Línea "Fdo.: …" abajo del bloque
    fdo_trabajador = f"Fdo.: {trabajador_full}"
    fdo_empresa = "Fdo.: representante legal"
    pdf.set_xy(x_left, y_sig + SIG_BLOCK_H - 6)
    pdf.cell(box_w, 5, " " + fdo_trabajador, border=0, align="L")
    pdf.set_xy(x_right, y_sig + SIG_BLOCK_H - 6)
    pdf.cell(box_w, 5, " " + fdo_empresa, border=0, align="L")

    return bytes(pdf.output())
