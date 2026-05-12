# Generador de Registros de Jornada

Aplicación web ligera para generar **hojas mensuales de registro de jornada
laboral** en PDF para empleados del Principado de Asturias.

Es una herramienta de generación documental, no de control horario: no graba
fichajes ni hashes encadenados — solo produce el PDF a partir de los datos
del empleado, la jornada tipo y los días no trabajados.

Pensada para alojarse en un **servidor de red local** (LAN o VPN). Cada
empleado accede con su **DNI** (sin contraseña) a su área personal y solo ve
sus propios registros. Un **administrador** gestiona empresas, centros,
empleados y usuarios.

## Características

- Login por **DNI** (sin contraseña) con dos roles: **admin** y **usuario**.
- CRUD de **empresas**, **centros de trabajo**, **empleados** y **usuarios**
  (solo accesible para admin).
- Asistente paso a paso que genera la **Hoja Mensual de Registro de Jornada**
  (PDF A4 con cabecera de empresa/trabajador, tabla diaria, totales y firmas).
- **Festivos del Principado de Asturias** (nacionales + autonómicos)
  precargados para 2024–2027.
- Cada PDF generado **se guarda en BBDD** con sus parámetros, lo que permite
  regenerarlo idéntico o editarlo posteriormente.
- Persistencia en **SQLite con modo WAL** — sin servicios externos.

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

## Setup en una nueva máquina

Hay dos formas de arrancar. **Elige una.**

### Opción A · Entorno virtual Windows (recomendado si ya tienes Python en Windows)

Aísla por completo las dependencias de esta app del Python global del sistema.

```cmd
:: 1) Clonar el repo
git clone https://github.com/Caleyero/RegistroJornada.git
cd RegistroJornada

:: 2) Crear el entorno virtual e instalar deps (una sola vez)
setup.bat
```

A partir de aquí: doble-click en `start.bat` y la app arranca con el `.venv\`
local. Si `setup.bat` detecta que `.venv\` ya existe, solo actualiza las
dependencias.

**¿Por qué venv?** Las dependencias de esta app (FastAPI 0.129, Pydantic 2.x,
SQLAlchemy 2.0, etc.) se quedan dentro de `.venv\` y no afectan a tu Python
global, donde puedes seguir teniendo `camelot`, `streamlit`, `marker`,
`langchain` u otras versiones distintas para otros proyectos.

### Opción B · WSL Ubuntu (sin Python en Windows)

```bash
cd /mnt/c/Users/<tu-usuario>/Documentos/RegistroJornada
pip3 install -r requirements.txt   # o mejor: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

Después doble-click en `start.bat`. Como no hay `.venv\` Windows, `start.bat`
delega en WSL.

### Menú interactivo

Doble-click en `menu.bat` para tener todas las acciones a mano:

1. Estado del repo (`estado.bat`)
2. Bajar cambios desde GitHub (`bajar.bat`)
3. Subir cambios a GitHub (`subir.bat`)
4. Arrancar la app (`start.bat`)

### Datos persistidos

La BBDD SQLite vive en `data/registro.db` y está en `.gitignore`. Si quieres
copiar los datos a otra máquina, llévate ese fichero aparte (no por git). Si
no, la BBDD se recrea vacía en el primer arranque.

### Requisitos

- Python 3.10+ en Windows **o** en WSL Ubuntu.
- Acceso al repo en GitHub (token HTTPS o clave SSH).
- (Solo Opción B) WSL2 con distro `Ubuntu`. Si tu distro se llama distinto,
  edita `-d Ubuntu` en los `.bat` o usa `wsl -l -q` para ver el nombre real.

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

## Autenticación y roles

La aplicación tiene dos roles:

- **Admin**: gestiona empresas, centros, empleados, usuarios y ve todos los
  registros generados.
- **Usuario**: solo ve y genera **sus propios** registros (los del empleado
  vinculado a su usuario). No tiene acceso al resto de la administración.

El login es **únicamente por DNI**, sin contraseña. El admin da de alta a
cada usuario asociándolo a un empleado existente desde
`/admin/usuarios/nuevo`.

> ⚠️ **Aviso de seguridad.** Cualquier persona con acceso a la red interna
> que conozca un DNI dado de alta podrá entrar como ese usuario. Este
> esquema solo es aceptable en una **red local estrictamente controlada**
> (VPN o LAN física confiable). **No exponer este servicio a Internet** sin
> añadir un mecanismo de autenticación adicional (p.ej. contraseña, MFA o
> reverse-proxy con autenticación corporativa).

### Bootstrap del administrador

Al arrancar, la app lee la variable `ADMIN_DNI` del `.env`:

- Si el usuario con ese DNI **no existe**, se crea con rol admin (idempotente
  en cada arranque).
- Si **existe pero es usuario normal**, se promueve a admin.
- Si **ya es admin**, no se hace nada.

Si `ADMIN_DNI` está vacío, no se hace bootstrap y debes crear al admin
manualmente (no recomendado tras un despliegue limpio).

### Sesión

La sesión se mantiene en una **cookie firmada** (HttpOnly) con `SECRET_KEY`.
Rotar `SECRET_KEY` en el `.env` invalida todas las sesiones activas y
fuerza a los usuarios a volver a entrar — útil si sospechas que la clave
ha sido comprometida.

## Configuración (.env)

| Variable               | Por defecto                  | Descripción                                                              |
|------------------------|------------------------------|--------------------------------------------------------------------------|
| `APP_HOST`             | `0.0.0.0`                    | Host de uvicorn (usar `0.0.0.0` para servir a la LAN, `127.0.0.1` solo local) |
| `APP_PORT`             | `8600`                       | Puerto                                                                   |
| `DATABASE_URL`         | `sqlite:///./data/registro.db` | Ruta del fichero SQLite                                                  |
| `APP_ENV`              | `development`                | Modo (development habilita `--reload`)                                   |
| `SECRET_KEY`           | *(obligatorio)*              | Token hex para firmar la cookie de sesión. Generar con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_DNI`            | *(vacío)*                    | DNI del admin inicial. Se crea/promueve al arrancar.                     |
| `SESSION_COOKIE_NAME`  | `registro_jornada_session`   | Nombre de la cookie de sesión.                                            |

## Despliegue en red local

### Resumen

- **Servidor**: Windows Server con NSSM (patrón del proyecto hermano
  `Entradas`). Para Linux, adapta a un unit de systemd.
- **`APP_HOST=0.0.0.0`** para que uvicorn escuche en todas las interfaces.
- **Firewall**: abrir el puerto (`8600` por defecto) **solo desde la
  subred interna**. No exponer al exterior.
- **Reverse proxy** (opcional): nginx / IIS / Caddy delante para terminar
  TLS interno si tienes certificados de tu CA corporativa.

### Despliegue automatizado (Windows Server)

El repo incluye dos scripts PowerShell que automatizan todo el ciclo
sobre un servidor Windows:

| Script                       | Cuándo usarlo                                                     |
|------------------------------|-------------------------------------------------------------------|
| `install-service.ps1`        | **Una sola vez**, primera instalación en el servidor.             |
| `deploy-to-server2022.ps1`   | **Cada actualización** (parar, sincronizar, reinstalar deps, arrancar). |

Edita las variables al principio de **ambos** scripts para que coincidan
(`$server`, `$rootRemote`, `$serviceName`, `$servicePort`). Por defecto:

```powershell
$server      = "192.168.1.222"
$rootRemote  = "C:\apps\RegistroJornada"
$serviceName = "registrojornada-backend"
$servicePort = 8600
```

#### Pre-requisitos en el servidor

- Windows Server 2019/2022.
- Python 3.10+ en `PATH` (`python --version`).
- NSSM en `PATH` o en `C:\Windows\System32\nssm.exe` (descargar de
  <https://nssm.cc/>).
- PSRemoting habilitado: `Enable-PSRemoting -Force` desde PowerShell admin.
- Share administrativo `c$` accesible desde tu máquina dev.

#### Pre-requisitos en tu máquina dev

Si conectas por IP (en lugar de nombre NetBIOS), configura una sola vez:

```powershell
winrm set winrm/config/client '@{TrustedHosts="192.168.1.222"}'
```

#### Flujo

```powershell
# Primera vez:
.\install-service.ps1
# Te pedirá credenciales del servidor (las cachea encriptadas), el DNI
# del admin inicial, y se encargará del resto: copia inicial, .env con
# SECRET_KEY autogenerada, venv, pip install, regla firewall, servicio
# NSSM con autostart, arranque y verificación de /health.

# A partir de aquí, para subir cambios:
.\deploy-to-server2022.ps1
# Para servicio → robocopy /MIR → pip install → arranca → verifica.
```

#### Qué NO se sobrescribe en cada deploy

`deploy-to-server2022.ps1` excluye del `robocopy /MIR` lo que es estado
de producción:

- `.env` (configuración).
- `data/` (la BBDD SQLite y sus ficheros WAL).
- `logs/`.

Edita estos directamente en el servidor cuando haga falta. Todo lo demás
queda como espejo exacto del repo dev — **no edites código a mano en el
servidor**, se perderá en el siguiente deploy.

### Backups de la BBDD

En modo WAL, SQLite genera tres ficheros que deben copiarse juntos:

- `data/registro.db`
- `data/registro.db-wal`
- `data/registro.db-shm`

Alternativamente (recomendado para snapshots consistentes en un único
fichero):

```powershell
sqlite3 C:\apps\RegistroJornada\data\registro.db `
    ".backup C:\backups\registro-$(Get-Date -Format yyyyMMdd-HHmm).db"
```

Programa esto como tarea diaria en el **Programador de tareas** de Windows.

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
