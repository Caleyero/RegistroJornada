# Generador de Registros de Jornada

Aplicación web ligera para generar **hojas mensuales de registro de jornada
laboral** en PDF para empleados del Principado de Asturias.

Es una herramienta de generación documental, no de control horario: no graba
fichajes ni hashes encadenados — solo produce el PDF a partir de los datos
del empleado, la jornada tipo y los días no trabajados.

## Características

- CRUD de **empresas**, **centros de trabajo** y **empleados**.
- Asistente paso a paso que genera la **Hoja Mensual de Registro de Jornada**
  (PDF A4 con cabecera de empresa/trabajador, tabla diaria, totales y firmas).
- **Festivos del Principado de Asturias** (nacionales + autonómicos)
  precargados para 2024–2027.
- Cada PDF generado **se guarda en BBDD** con sus parámetros, lo que permite
  regenerarlo idéntico o editarlo posteriormente.
- Persistencia en **SQLite** — sin servicios externos.

## Requisitos

- Python 3.10+ (probado en 3.12)
- pip

## Puesta en marcha

```bash
# 1) Copiar variables de entorno
cp .env.example .env

# 2) Instalar dependencias
pip install -r requirements.txt

# 3) (Opcional) Crear datos de demo
python -m scripts.init_db --demo

# 4) Arrancar
bash run.sh
# Windows: doble click en start.bat
```

Abre <http://127.0.0.1:8600/> en el navegador.

## Setup en una nueva máquina (Windows + WSL Ubuntu)

```cmd
:: 1) Clonar el repo en cualquier ruta de Windows
git clone https://github.com/Caleyero/RegistroJornada.git
cd RegistroJornada
```

Después, una sola vez, dentro de WSL:

```bash
# (Sustituye la ruta por la real donde clonaste)
cd /mnt/c/Users/<tu-usuario>/Documentos/RegistroJornada
pip3 install -r requirements.txt
```

A partir de aquí:

- **Doble-click en `menu.bat`** → menú interactivo con 4 opciones:
  1. Estado del repo (`estado.bat`)
  2. Bajar cambios desde GitHub (`bajar.bat`)
  3. Subir cambios a GitHub (`subir.bat`)
  4. Arrancar la app (`start.bat` — uvicorn + abre el navegador)
- O usa los `.bat` sueltos directamente.

La BBDD SQLite se crea automáticamente al primer arranque dentro de `data/`,
que está en `.gitignore`. Si quieres llevarte los datos de otra máquina, copia
`data/registro.db` aparte (no por git).

### Requisitos en la nueva máquina

- WSL2 con distro **Ubuntu** (si tu distro tiene otro nombre, edita `-d Ubuntu`
  en los `.bat` de la raíz o usa `wsl -l -q` para ver el nombre real).
- Python 3.10+ en WSL (`python3 --version`).
- Acceso al repo en GitHub (token HTTPS o clave SSH).

## Estructura

```
app/
  config.py              Settings
  database.py            Engine SQLite + Base
  dependencies.py        get_db
  main.py                FastAPI + montaje de routers/static
  models/                Empresa, CentroTrabajo, Empleado, Registro
  routers/               empresas, centros, empleados, registros (wizard + historial)
  services/
    festivos.py          FESTIVOS_ASTURIAS (2024-2027)
    pdf_service.py       Generación del PDF mensual con fpdf2
  static/
    css/custom.css
    fonts/               Consolas TTF para el PDF
  templates/             base + dashboard + CRUDs + wizard + historial
data/registro.db         BBDD SQLite (auto-creada)
scripts/init_db.py       Crea tablas y datos demo
```

## Configuración (.env)

| Variable        | Por defecto                  | Descripción                            |
|-----------------|------------------------------|----------------------------------------|
| `APP_HOST`      | `127.0.0.1`                  | Host de uvicorn                        |
| `APP_PORT`      | `8600`                       | Puerto                                 |
| `DATABASE_URL`  | `sqlite:///./data/registro.db` | Ruta del fichero SQLite               |
| `APP_ENV`       | `development`                | Modo (development habilita `--reload`) |

## Festivos

Los festivos del Principado de Asturias para 2026 (Resolución del BOPA) están
hardcodeados en `app/services/festivos.py`. Cada año hay que verificarlos con
la publicación oficial. En el wizard puedes añadir o quitar festivos puntuales
sin tocar el código.

## Diferencias con KRONOS

| KRONOS                                | RegistroJornada                        |
|---------------------------------------|----------------------------------------|
| Control horario completo              | Solo generación de PDFs mensuales      |
| PostgreSQL + Alembic                  | SQLite                                 |
| Auth JWT con roles                    | Sin autenticación (uso local)          |
| Fichajes inmutables + hash chain      | —                                      |
| Auditoría, invitaciones, email        | —                                      |
| Multi-empresa con permisos            | Multi-empresa simple                   |
