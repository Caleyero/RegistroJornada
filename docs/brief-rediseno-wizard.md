# Brief de rediseño · Asistente de Registro Mensual

## 1. Resumen

Pantalla principal de una aplicación web ligera que **genera la hoja mensual
de registro de jornada laboral** (PDF) para empleados del Principado de
Asturias. La pantalla es un único formulario tipo "wizard" en una sola
página: el usuario rellena horario, festivos, vacaciones y ausencias, ve
una vista previa del mes en un calendario, y pulsa un botón para descargar
el PDF (que además se guarda en BBDD para regenerarlo después).

**Lo que hay que rediseñar:** la página `/registros/nuevo` — el formulario
de captura, el bloque de festivos, el bloque de vacaciones/ausencias y el
calendario de vista previa. **No** se rediseña el PDF resultante (eso ya
tiene un diseño aprobado).

## 2. Contexto del producto

- **Nombre interno**: Generador de Registros de Jornada
- **Stack**: FastAPI + Jinja2 + Bootstrap 5 + vanilla JS (sin frameworks)
- **Persistencia**: SQLite, local
- **Uso**: 100% local, sin login, una persona la opera desde su navegador
- **No** es una herramienta de control horario en tiempo real; sólo produce
  el PDF mensual a partir de datos introducidos manualmente.

## 3. Audiencia y contexto de uso

- **Quién**: un administrador (RRHH / gerente / asesoría) que prepara los
  registros legales de jornada de un grupo pequeño de empleados.
- **Dispositivo**: escritorio principalmente (Windows + Chrome). Móvil no
  es prioritario, pero no debe romperse en tablet.
- **Frecuencia**: una vez al mes por empleado. Es probable que el usuario
  rellene varios meses seguidos para distintos empleados — el flujo
  "siguiente registro" debe ser ágil.
- **Nivel técnico**: medio. Conoce conceptos como "festivo", "jornada",
  "NIF", "NAF", pero no tiene paciencia para flujos largos.

## 4. Qué hace la página actualmente

El usuario ve **un único formulario** dividido en 6 bloques secuenciales
en vertical:

| Paso | Bloque | Comportamiento |
|------|---------------------------|----------------------------------------------------|
| 1    | Empleado y periodo        | Selector de empleado (lista filtrada por activos), año (input number), mes (select 1-12). |
| 2    | Jornada laboral           | Checkboxes de días laborables (lun-dom; por defecto L-V) + 4 horas: inicio jornada, inicio pausa, fin pausa, fin jornada. |
| 3    | Festivos del mes          | Auto-rellenados desde una lista de festivos del Principado de Asturias. El usuario puede borrar los que no apliquen o añadir uno extra (fecha + descripción). |
| 4    | Vacaciones                | Checkbox "el empleado disfrutó vacaciones". Si lo activa, aparece un rango "Desde / Hasta" y los días se acumulan en una lista. También se pueden marcar día a día en el calendario (paso 6). |
| 5    | Ausencias justificadas    | Fechas con motivo (cita médica, permiso…), funcionan igual que un festivo puntual. |
| 6    | Vista previa del mes      | Calendario tabular (7 cols, lun-dom). Cada celda muestra el día, su tipo (laborable / no-laborable / festivo / vacaciones / ausencia) y permite alternar "vacaciones" haciendo clic en un día laborable. Bajo el calendario, contador de horas estimadas del mes. |

Al pulsar **"Generar PDF y guardar"** se manda un POST con todos los
datos a `/registros/generar`, el backend guarda el registro en BBDD y
devuelve el PDF que el navegador descarga.

### Reglas de interacción importantes

- Cambiar año/mes recarga los festivos del mes y filtra vacaciones/
  ausencias para que solo queden las del nuevo mes.
- Al añadir un día de vacaciones manualmente desde el calendario, debe
  marcarse automáticamente el checkbox "el empleado disfrutó vacaciones".
- Los festivos auto-rellenados son una "sugerencia" — el usuario debe
  poder quitarlos uno a uno sin perder la lista completa.
- Las cuatro horas (inicio jornada, inicio pausa, fin pausa, fin jornada)
  son siempre obligatorias aunque el mes tenga 0 días laborables (no se
  valida en cliente, sí en servidor).

## 5. Datos capturados (contrato con el backend)

El formulario produce un **único JSON** con esta forma exacta — no debe
cambiarse, el backend lo valida con Pydantic:

```json
{
  "empleado_id": 12,
  "anio": 2026,
  "mes": 2,
  "dias_laborables": [0, 1, 2, 3, 4],
  "inicio_jornada": "10:00",
  "inicio_pausa": "14:00",
  "fin_pausa": "14:30",
  "fin_jornada": "18:30",
  "festivos":   {"2026-02-15": "Carnaval"},
  "vacaciones": ["2026-02-23", "2026-02-24"],
  "ausencias":  {"2026-02-10": "Cita médica"}
}
```

Validaciones en cliente (alertas tipo `alert()`):

- Se debe seleccionar un empleado.
- Se debe marcar al menos un día laborable.
- Para añadir un rango de vacaciones, "Desde" ≤ "Hasta".
- Añadir festivo / ausencia requiere fecha.

## 6. Qué se genera

Al enviar el formulario, el backend devuelve un PDF A4 vertical de una
página (mockup ya definido y fuera del alcance del rediseño):

- Cabecera con datos de empresa y trabajador.
- Tabla diaria de 28-31 filas con inicio/pausa/fin/horas y observaciones.
- Total mensual de horas trabajadas.
- Cajas de firma del trabajador y la empresa.

Diseño actual del PDF en `app/services/pdf_service.py`.

## 7. Restricciones técnicas

- **HTML+CSS+JS solamente** — no es un SPA. La página la sirve Jinja2
  desde el backend; el JS es vanilla (sin React/Vue/Alpine).
- **Bootstrap 5.3** ya cargado por CDN — se pueden usar sus componentes
  (`.row`, `.col`, `.card`, `.form-control`, `.btn`, `.badge`, etc.) y
  los iconos de **Bootstrap Icons** (`<i class="bi bi-..."></i>`).
- CSS personalizado vive en `app/static/css/custom.css`.
- El template extiende `base.html`, que aporta una `<nav>` superior con
  enlaces a Empresas / Centros / Empleados / Historial / Nuevo registro.
- El idioma de la interfaz es **español**.

### ¿Qué se puede cambiar libremente?

- Estructura visual (1 columna vs 2 columnas, tabs, acordeón, stepper…).
- Tipografía, colores, espaciados, iconos.
- Reagrupación de los 6 bloques (p.ej. fusionar festivos+vacaciones+
  ausencias en un sidebar lateral junto al calendario).
- Reescribir el JS si hace falta — siempre que el JSON enviado al servidor
  mantenga el formato exacto del apartado 5.

### ¿Qué NO se puede cambiar?

- El endpoint de envío: `POST /registros/generar` con el JSON del
  apartado 5.
- El listado de empleados que se inyecta por Jinja desde el servidor
  (cada `<option>` lleva `data-empresa` y `data-centro`).
- El diccionario `FESTIVOS_ASTURIAS` que se inyecta también por Jinja
  (clave fecha ISO, valor descripción).

## 8. Ficheros de referencia (entregables al diseñador)

| Archivo                              | Para qué                                 |
|--------------------------------------|------------------------------------------|
| `app/templates/registros/wizard.html`| **Pantalla actual a rediseñar**          |
| `app/templates/base.html`            | Layout/navbar global, no rediseñar       |
| `app/static/css/custom.css`          | CSS actual del wizard (clases `.day-cell`, `.festivo-item`, etc.) |
| `app/services/festivos.py`           | Lista de festivos preconfigurados (input dinámico) |
| `docs/diseno/pdf-mockup.pdf` *(opc.)*| Diseño del PDF resultante (para referencia visual del estilo general del producto) |

Sugerencia: adjuntar también una **captura de pantalla** de la página
actual en `docs/diseno/wizard-actual.png` para que el diseñador vea el
punto de partida.

## 9. Cómo entregar el rediseño

Cualquiera de estas tres formas vale:

1. **Mockup en imagen** (PNG/PDF) + lista de cambios funcionales.
2. **HTML+CSS** que sustituyan los bloques `{% block content %}` y
   `{% block extra_css %}` del template actual (sin tocar el `<script>`,
   o reescribiéndolo si está justificado).
3. **Figma** público o exportable.

Si el rediseño introduce nuevos campos o flujos no contemplados aquí,
indicarlo explícitamente en una sección "cambios funcionales" — pueden
requerir cambios en el backend (modelo `Registro` y endpoint), que se
tratarán en una segunda iteración.

## 10. Inspiración / tono

- Producto interno, no comercial. Estética **sobria, densa en información,
  monoespaciada en zonas tabulares** — alineada con el PDF resultante.
- Paleta neutra (blancos, grises, un acento puntual). Evitar gradientes,
  sombras grandes o microinteracciones que ralenticen.
- Pensado para un usuario que rellena varios registros seguidos: prioridad
  a la **velocidad de tabulación** y al **resumen visual del mes** en el
  calendario.
