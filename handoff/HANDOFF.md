# Entrega · Rediseño de `/registros/nuevo`

Variante elegida: **V2 · dos columnas con vista previa sticky + acordeón**.

## Archivos

```
handoff/
├── templates/registros/wizard.html   ← sustituye app/templates/registros/wizard.html
├── static/css/registros-wizard.css   ← copiar a app/static/css/registros-wizard.css
└── HANDOFF.md                        ← este documento
```

## Pasos de integración

1. **Copia la hoja de estilos**
   ```bash
   cp handoff/static/css/registros-wizard.css app/static/css/registros-wizard.css
   ```
   No reemplaces `custom.css`. El template ya incluye un `<link>` dentro de
   `{% block extra_css %}` que la carga sólo en esta pantalla.

2. **Sustituye el template**
   ```bash
   cp handoff/templates/registros/wizard.html app/templates/registros/wizard.html
   ```

3. **Verifica el contrato con el backend** — no debería hacer falta tocar nada.
   El JSON enviado a `POST /registros/generar` sigue siendo idéntico al de la
   versión anterior:
   ```json
   {
     "empleado_id": 12,
     "anio": 2026,
     "mes": 5,
     "dias_laborables": [0,1,2,3,4],
     "inicio_jornada": "10:00",
     "inicio_pausa":  "14:00",
     "fin_pausa":     "14:30",
     "fin_jornada":   "18:30",
     "festivos":   {"2026-05-26": "MARTES DE CAMPO"},
     "vacaciones": ["2026-05-04", "2026-05-05"],
     "ausencias":  {"2026-05-12": "Cita médica"}
   }
   ```

4. **Contexto que sigue inyectando la vista** (sin cambios respecto al actual):
   - `empleados_lista` — empleados activos con `empresa` y `centro_trabajo`.
   - `festivos_asturias` — dict `{ "YYYY-MM-DD": "descripción" }`.
   - `anio_default`, `mes_default` — enteros.
   - `registro_existente` (opcional) — registro previo a precargar en el wizard.

## Cambios respecto al wizard antiguo

### Estructura visual
- Layout en **dos columnas** con vista previa pegada a la derecha (sticky).
  Bajo 1180 px de viewport pasa a una columna y la previsualización se sitúa
  debajo.
- Los 6 bloques originales se reagrupan en **3 acordeones** colapsables:
  1. *Empleado y periodo* — empleado + año + mes.
  2. *Horario tipo* — días laborables (botones cuadrados) + 4 horas.
  3. *Eventos del mes* — pestañas Festivos / Vacaciones / Ausencias.
- Cabecera de página con badge de estado `SIN CAMBIOS / BORRADOR · SIN GUARDAR`.

### Visual
- Paleta monocroma: 4 niveles de negro/gris + un tinte cálido para fondos.
  Sólo un acento muy suave (`--tint`) en celdas de vacaciones.
- Tipografía **Consolas** en todos los datos (inputs, números, etiquetas).
  Sans para títulos y descripción del bloque.
- Iconografía mínima: flechas Unicode y bordes/casillas geométricas.
  **No se usa Bootstrap Icons** en esta pantalla.

### Interacciones nuevas
- **Clic** en un día del calendario alterna VACACIONES (sólo días laborables
  sin festivo/ausencia). Si no hay ninguna vacación marcada y se añade la
  primera, el toggle de la pestaña *Vacaciones* se activa automáticamente.
- **Mayús + clic** marca un rango entre el último día tocado y el actual.
- **⌘/Ctrl + S** dispara *Generar PDF y guardar*.
- El header de cada acordeón muestra un resumen vivo cuando el bloque está
  cerrado (`L–V · 10:00 → 18:30`, `2 festivos · 0 vacaciones · 0 ausencias`).
- Pestañas con contador en cada solapa (`FESTIVOS · 2`).
- Tabla con columna *Origen* (`Auto` vs `Manual`) para distinguir los festivos
  pre-cargados de los añadidos por el usuario.

### Compatibilidad
- Bootstrap 5.3 sigue cargado por `base.html` pero esta pantalla **ya no usa
  clases Bootstrap**. Si en el futuro se desactivara Bootstrap para esta vista,
  no rompería nada.
- Las clases CSS quedan namespaced por bloque (`.block`, `.cal`, `.preview`,
  `.tab`, …) sin colisión con `.btn` de Bootstrap (usamos `.btn--primary`,
  `.btn--ghost`, etc).

## Cambios funcionales propuestos (NO incluidos en esta entrega)

Estos cambios requerirían tocar el backend; se mantienen *fuera de scope*:

- Plantillas guardadas de jornada (mañana / partida / turno) — añadiría un
  endpoint `GET /horarios/plantillas`.
- Edición de horario *por día concreto* — supondría ampliar el modelo
  `Registro` con `overrides_diarios: dict[fecha, horario]`.
- Auto-guardado a medida que se rellena — endpoint `PATCH /registros/borrador`.

## Validaciones cliente

Idénticas al wizard antiguo, con `alert()` simple:

- `empleado` obligatorio.
- Al menos un día laborable marcado.
- Rango de vacaciones con `desde <= hasta`.
- Fecha obligatoria para añadir festivo / ausencia.

## QA sugerido

1. Cargar `/registros/nuevo`, verificar que el calendario muestra mayo 2026
   con los festivos auto-rellenados (1 may, 26 may) en negro.
2. Cambiar a febrero — debe recargar los festivos del nuevo mes y vaciar
   vacaciones/ausencias.
3. Marcar 3 días en el calendario → contador *Vacaciones* a 3, total horas baja.
4. Desmarcar todos los `.dia` excepto sábado → el calendario debe mostrar
   sólo los sábados como laborables.
5. `⌘+S` → debe descargar el PDF con el mismo formato que el wizard anterior.
6. Recargar un registro existente vía `registro_existente` — todos los campos
   y el calendario se restauran (la función `aplicarRegistroExistente` original
   sigue sin estar implementada en este entregable: ver TODO en el JS).

## TODO conocido

- [ ] Re-implementar `aplicarRegistroExistente(REGISTRO_EXISTENTE)` en el JS
  del template (sólo se ha mantenido la lectura del valor; falta la rama que
  rellena campos desde un registro previo). Comportamiento esperado: igual al
  wizard anterior.
- [ ] Considerar mover los estilos a una capa `@layer` para que cualquier
  override de Bootstrap se resuelva sin `!important`.
