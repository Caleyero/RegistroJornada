# Setup inicial de RegistroJornada en un servidor Windows (primera vez)
# Uso: .\install-service.ps1
#
# Hace TODO el trabajo la primera vez:
#   1. Verifica acceso a \\<server>\c$\apps\RegistroJornada.
#   2. Pide credenciales de admin del server (cachea para futuros deploys).
#   3. Copia inicial del repo al server (robocopy /E, NO /MIR).
#   4. Crea o verifica .env en el server (interactivo si falta).
#   5. Crea venv y `pip install -r requirements.txt` remotamente.
#   6. Abre el puerto 8600 en el firewall (solo desde la LAN).
#   7. Instala servicio Windows registrojornada-backend con NSSM.
#   8. Arranca el servicio y verifica /health.
#
# Tras ejecutar esto una vez con exito, para actualizar el codigo basta
# con .\deploy-to-server2022.ps1 (ese script asume servicio ya instalado).
#
# REQUISITOS PREVIOS EN EL SERVIDOR:
#   - Windows Server (probado en Windows Server 2022).
#   - Python 3.10+ instalado y en PATH (verificar con `python --version`).
#   - NSSM en PATH o en C:\Windows\System32\ (descargar de https://nssm.cc/).
#   - PSRemoting habilitado: Enable-PSRemoting -Force.
#   - Share administrativo c$ accesible desde tu maquina.
#
# REQUISITOS EN TU MAQUINA DEV:
#   - Si conectas por IP en lugar de nombre, configura TrustedHosts:
#       winrm set winrm/config/client '@{TrustedHosts="192.168.1.222"}'

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# Configuracion (ajusta si tu entorno difiere)
# ----------------------------------------------------------------------
$server         = "192.168.1.222"
$rootRemote     = "C:\apps\RegistroJornada"
$dst            = "\\$server\c$\apps\RegistroJornada"
$serviceName    = "registrojornada-backend"
$servicePort    = 8600
$healthUrl      = "http://${server}:${servicePort}/health"
$pythonRemote   = "python"                                         # se resuelve via PATH del server
$venvPython     = "$rootRemote\.venv\Scripts\python.exe"
$logFileRemote  = "$rootRemote\logs\service.log"

$credCacheDir   = "$env:LOCALAPPDATA\registrojornada"
$credCachePath  = "$credCacheDir\deploy-credential.xml"

$src            = $PSScriptRoot

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
function Write-Step($msg) {
    Write-Host ""
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

function Write-Hint($msg) {
    Write-Host "  $msg" -ForegroundColor DarkGray
}

function Get-Or-Prompt-Credential {
    if (Test-Path $credCachePath) {
        try { return Import-Clixml -Path $credCachePath } catch { }
    }
    Write-Host ""
    Write-Host "Necesito las credenciales de admin de $server." -ForegroundColor Yellow
    Write-Hint "Se guardaran encriptadas en $credCachePath"
    $defaultUser = "Administrador"
    $userInput = Read-Host "Usuario [$defaultUser]"
    if ([string]::IsNullOrWhiteSpace($userInput)) { $userInput = $defaultUser }
    $securePass = Read-Host "Password" -AsSecureString
    if (-not $securePass -or $securePass.Length -eq 0) {
        throw "Sin password no se puede continuar."
    }
    $cred = New-Object System.Management.Automation.PSCredential($userInput, $securePass)
    if (-not (Test-Path $credCacheDir)) {
        New-Item -ItemType Directory -Path $credCacheDir -Force | Out-Null
    }
    $cred | Export-Clixml -Path $credCachePath
    Write-Host "Credenciales guardadas." -ForegroundColor Green
    return $cred
}

# ----------------------------------------------------------------------
Write-Step "Setup inicial de RegistroJornada en $server"
Write-Host "Origen:  $src"
Write-Host "Destino: $dst"

# --- Acceso SMB ------------------------------------------------------
if (-not (Test-Path "\\$server\c$")) {
    Write-Host ""
    Write-Host "ERROR: no se puede acceder a \\$server\c$" -ForegroundColor Red
    Write-Hint "Comprueba que el servidor esta encendido, que tu usuario tiene acceso"
    Write-Hint "al share administrativo c$ y que el firewall no esta bloqueando SMB (445)."
    exit 1
}

# Crear carpeta raiz remota si no existe
if (-not (Test-Path $dst)) {
    Write-Host "Creando $dst..." -ForegroundColor DarkGray
    New-Item -ItemType Directory -Path $dst -Force | Out-Null
}

$cred = Get-Or-Prompt-Credential

# --- Copia inicial (robocopy /E, sin mirror) ------------------------
Write-Step "[1/7] Copiando ficheros iniciales a $dst"
# Nombres RELATIVOS para que /XD coincida tanto en origen como en destino
# (las rutas absolutas solo se evaluan contra el origen y /MIR borraria
# directorios EXTRA del destino).
$excludeDirs = @(
    ".git",
    ".venv",
    "__pycache__",
    "data",
    "logs",
    "handoff",
    ".pytest_cache",
    ".mypy_cache",
    ".claude"
)
$excludeFiles = @(
    "*.pyc",
    "*.pyo",
    "*.log",
    ".env",
    ".env.local",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.sqlite",
    "*.sqlite3"
)
$roboArgs = @(
    $src, $dst,
    "/E",
    "/Z",
    "/R:2", "/W:2",
    "/NFL", "/NDL", "/NP",
    "/XJ",
    "/IS",
    "/FFT"
)
foreach ($d in $excludeDirs)  { $roboArgs += "/XD"; $roboArgs += $d }
foreach ($f in $excludeFiles) { $roboArgs += "/XF"; $roboArgs += $f }
robocopy @roboArgs
$rc = $LASTEXITCODE
if ($rc -ge 8) {
    Write-Host "ERROR: robocopy fallo con codigo $rc" -ForegroundColor Red
    exit 1
}
Write-Host "Copia inicial completada." -ForegroundColor Green

# Crear carpetas que excluimos del robocopy
foreach ($sub in @("data", "logs")) {
    $p = "$dst\$sub"
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}

# --- .env: crear si no existe ---------------------------------------
Write-Step "[2/7] Verificando .env en $server"
$envPath = "$dst\.env"
if (-not (Test-Path $envPath)) {
    Write-Host "No hay .env todavia. Lo creo ahora." -ForegroundColor Yellow
    $adminDni = Read-Host "DNI del administrador inicial (sera promovido a admin)"
    $adminDni = $adminDni.Trim().ToUpper()
    if ([string]::IsNullOrWhiteSpace($adminDni)) {
        Write-Host "ERROR: necesito un DNI para el admin inicial." -ForegroundColor Red
        exit 1
    }
    # SECRET_KEY: 32 bytes aleatorios en hex usando RNG criptografico de .NET
    # (no depende de tener Python en PATH del cliente).
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secretKey = ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''
    $envContent = @"
APP_NAME=Generador de Registros de Jornada
APP_HOST=0.0.0.0
APP_PORT=$servicePort
APP_ENV=production

DATABASE_URL=sqlite:///./data/registro.db

SECRET_KEY=$secretKey

ADMIN_DNI=$adminDni
"@
    # IMPORTANTE: Set-Content -Encoding UTF8 en Windows PowerShell 5.x escribe
    # UTF-8 CON BOM, y python-dotenv interpreta el BOM como parte de la primera
    # clave (APP_NAME -> [BOM-bytes]APP_NAME), rompiendo pydantic-settings.
    # Forzamos UTF-8 SIN BOM con la API de .NET.
    [System.IO.File]::WriteAllText($envPath, $envContent, (New-Object System.Text.UTF8Encoding $false))
    Write-Host ".env creado con SECRET_KEY generada y ADMIN_DNI=$adminDni." -ForegroundColor Green
} else {
    Write-Host ".env ya existe - no lo toco." -ForegroundColor Green
}

# --- Crear venv + pip install ---------------------------------------
Write-Step "[3/7] Creando virtualenv e instalando dependencias en $server"
$venvOut = Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock {
    param($root, $py)
    Set-Location $root

    if (-not (Test-Path "$root\.venv")) {
        & $py -m venv .venv 2>&1
        if ($LASTEXITCODE -ne 0) { return @("ERROR_VENV", $LASTEXITCODE) }
    }
    & "$root\.venv\Scripts\python.exe" -m pip install --upgrade pip 2>&1 | Out-Null
    & "$root\.venv\Scripts\python.exe" -m pip install -r "$root\requirements.txt" 2>&1
    return @("OK", $LASTEXITCODE)
} -ArgumentList $rootRemote, $pythonRemote

$marker = $venvOut[-2]
$exit   = $venvOut[-1]
if ($marker -eq "ERROR_VENV") {
    Write-Host "ERROR: fallo creando el venv (codigo $exit). Python esta en PATH del server?" -ForegroundColor Red
    exit 1
}
if ($exit -ne 0) {
    Write-Host "ERROR: pip install devolvio codigo $exit" -ForegroundColor Red
    Write-Host ($venvOut | Out-String)
    exit 1
}
Write-Host "Venv listo y dependencias instaladas." -ForegroundColor Green

# --- Regla de firewall (LAN) ----------------------------------------
Write-Step "[4/7] Abriendo puerto $servicePort en el firewall (solo subred local)"
$fwOut = Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock {
    param($port)
    $name = "RegistroJornada $port"
    $existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Output "YA_EXISTE"
        return 0
    }
    New-NetFirewallRule `
        -DisplayName $name `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $port `
        -RemoteAddress LocalSubnet `
        -Action Allow | Out-Null
    return $LASTEXITCODE
} -ArgumentList $servicePort
if ($fwOut -contains "YA_EXISTE") {
    Write-Host "Regla de firewall ya existia." -ForegroundColor Yellow
} else {
    Write-Host "Regla de firewall creada (LocalSubnet -> TCP $servicePort)." -ForegroundColor Green
}

# --- Instalar servicio NSSM -----------------------------------------
Write-Step "[5/7] Instalando servicio Windows $serviceName"
$svcOut = Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock {
    param($serviceName, $venvPython, $root, $logFile, $port)

    $existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Output "SERVICIO_YA_EXISTE"
        return 0
    }

    $nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
    if (-not $nssm) {
        foreach ($p in @(
            "C:\ProgramData\chocolatey\bin\nssm.exe",
            "C:\Windows\System32\nssm.exe",
            "C:\Tools\nssm\nssm.exe"
        )) {
            if (Test-Path $p) { $nssm = $p; break }
        }
    }
    if (-not $nssm) {
        Write-Output "NSSM_NO_ENCONTRADO"
        return 1
    }

    if (-not (Test-Path (Split-Path $logFile -Parent))) {
        New-Item -ItemType Directory -Path (Split-Path $logFile -Parent) -Force | Out-Null
    }

    & $nssm install $serviceName $venvPython -m uvicorn app.main:app --host 0.0.0.0 --port $port
    & $nssm set $serviceName AppDirectory $root
    & $nssm set $serviceName Start SERVICE_AUTO_START
    & $nssm set $serviceName AppStdout $logFile
    & $nssm set $serviceName AppStderr $logFile
    & $nssm set $serviceName AppRotateFiles 1
    & $nssm set $serviceName AppRotateOnline 1
    & $nssm set $serviceName AppRotateSeconds 86400
    & $nssm set $serviceName AppRotateBytes 20971520
    & $nssm set $serviceName Description "RegistroJornada - Generador de Hojas Mensuales (FastAPI en :$port)"

    return $LASTEXITCODE
} -ArgumentList $serviceName, $venvPython, $rootRemote, $logFileRemote, $servicePort

$marker = $svcOut | Where-Object { $_ -is [string] } | Select-Object -First 1
$exit   = $svcOut[-1]
if ($marker -eq "SERVICIO_YA_EXISTE") {
    Write-Host "El servicio $serviceName ya existe. Me salto la instalacion." -ForegroundColor Yellow
} elseif ($marker -eq "NSSM_NO_ENCONTRADO") {
    Write-Host "ERROR: NSSM no esta instalado o no esta en PATH en $server." -ForegroundColor Red
    Write-Hint "Descargalo de https://nssm.cc/download y copialo a C:\Windows\System32\nssm.exe."
    exit 1
} elseif ($exit -ne 0) {
    Write-Host "ERROR: NSSM devolvio codigo $exit" -ForegroundColor Red
    Write-Host ($svcOut | Out-String)
    exit 1
} else {
    Write-Host "Servicio instalado." -ForegroundColor Green
}

# --- Arrancar servicio ----------------------------------------------
Write-Step "[6/7] Arrancando servicio $serviceName"
try {
    Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock {
        param($name)
        Start-Service -Name $name -ErrorAction Stop
        $svc = Get-Service -Name $name
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 1
            $svc.Refresh()
            if ($svc.Status -eq "Running") { break }
        }
        if ($svc.Status -ne "Running") { throw "Timeout arrancando el servicio (estado: $($svc.Status))." }
    } -ArgumentList $serviceName
    Write-Host "Servicio arrancado." -ForegroundColor Green
} catch {
    Write-Host "ERROR arrancando servicio: $_" -ForegroundColor Red
    Write-Hint "Revisa el log: \\$server\c$\apps\RegistroJornada\logs\service.log"
    exit 1
}

# --- Verificar /health ----------------------------------------------
Write-Step "[7/7] Verificando backend"
$ok = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}

Write-Host ""
if ($ok) {
    Write-Host "Setup completado. Backend OK en $healthUrl" -ForegroundColor Green
    Write-Host ""
    Write-Host "Proximos pasos:" -ForegroundColor Cyan
    Write-Hint "- Abre http://${server}:${servicePort}/ y entra con tu DNI (ADMIN_DNI del .env)."
    Write-Hint "- Da de alta empresas, centros y empleados desde el panel."
    Write-Hint "- Crea usuarios para cada empleado desde /admin/usuarios."
    Write-Hint "- Para futuras actualizaciones del codigo: .\deploy-to-server2022.ps1"
} else {
    Write-Host "AVISO: servicio arrancado pero /health no responde tras 15s." -ForegroundColor Yellow
    Write-Hint "Revisa el log: \\$server\c$\apps\RegistroJornada\logs\service.log"
    exit 1
}
