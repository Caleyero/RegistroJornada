# Despliegue iterativo de RegistroJornada al servidor (un solo comando)
# Uso: .\deploy-to-server2022.ps1
#
# Hace todo el ciclo:
#   1. Para el servicio registrojornada-backend en el servidor.
#   2. Espeja el repo a \\<server>\c$\apps\RegistroJornada con robocopy /MIR.
#   3. Actualiza dependencias Python (pip install -r requirements.txt) remotamente.
#   4. Arranca el servicio.
#   5. Verifica /health.
#
# REQUISITOS:
#   - Servicio Windows registrojornada-backend ya instalado (lanza install-service.ps1 una vez).
#   - Acceso al share administrativo \\<server>\c$.
#   - Permiso para parar/arrancar servicios en el servidor desde este PC.
#
# IMPORTANTE: /MIR borra en destino lo que no exista en origen. El server queda
# como espejo exacto de dev. NO edites ficheros directamente en el server, se
# perderan en el siguiente despliegue. Excepciones excluidas del MIR:
#   - .env (config de produccion)
#   - data/ (la BBDD SQLite)
#   - logs/

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# Configuracion (debe coincidir con install-service.ps1)
# ----------------------------------------------------------------------
$server         = "192.168.1.222"
$rootRemote     = "C:\apps\RegistroJornada"
$dst            = "\\$server\c$\apps\RegistroJornada"
$serviceName    = "registrojornada-backend"
$servicePort    = 8600
$healthUrl      = "http://${server}:${servicePort}/health"
$venvPython     = "$rootRemote\.venv\Scripts\python.exe"

$credCacheDir   = "$env:LOCALAPPDATA\registrojornada"
$credCachePath  = "$credCacheDir\deploy-credential.xml"

$src            = $PSScriptRoot

# ----------------------------------------------------------------------
function Write-Step($msg) {
    Write-Host ""
    Write-Host "=== $msg ===" -ForegroundColor Cyan
}

function Get-Or-Prompt-Credential {
    if (Test-Path $credCachePath) {
        try { return Import-Clixml -Path $credCachePath } catch { }
    }
    Write-Host ""
    Write-Host "Necesito las credenciales de admin de $server." -ForegroundColor Yellow
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
    return $cred
}

function Try-Start-Service {
    try {
        Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock {
            param($name)
            Start-Service -Name $name
        } -ArgumentList $serviceName | Out-Null
    } catch { }
}

# ----------------------------------------------------------------------
Write-Step "Despliegue RegistroJornada -> $server"
Write-Host "Origen:  $src"
Write-Host "Destino: $dst"

if (-not (Test-Path $dst)) {
    Write-Host "ERROR: no se puede acceder a $dst" -ForegroundColor Red
    Write-Host "Comprueba que el servidor esta encendido y que la carpeta existe."
    Write-Host "(Si es el primer despliegue, lanza primero .\install-service.ps1)" -ForegroundColor Yellow
    exit 1
}

$cred = Get-Or-Prompt-Credential

# --- Parar servicio --------------------------------------------------
# Estrategia escalonada sin Stop-Service (Stop-Service bloquea 30s
# ignorando -ErrorAction Stop). Vamos directo a sc.exe stop (no bloquea),
# y si NSSM no se rinde matamos el arbol con taskkill /T /F.
Write-Step "[1/5] Parando servicio $serviceName"
try {
    $stopResult = Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock {
        param($name)
        $svc = Get-Service -Name $name -ErrorAction Stop
        if ($svc.Status -eq "Stopped") { return "YA_PARADO" }

        & sc.exe stop $name 2>&1 | Out-Null

        for ($i = 0; $i -lt 5; $i++) {
            Start-Sleep -Seconds 1
            $svc.Refresh()
            if ($svc.Status -eq "Stopped") { break }
        }
        if ($svc.Status -eq "Stopped") { return "PARADO_NORMAL" }

        $wmi = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue
        $rootPid = if ($wmi) { [int]$wmi.ProcessId } else { 0 }
        if ($rootPid -gt 0) {
            & taskkill.exe /PID $rootPid /T /F 2>&1 | Out-Null
            Start-Sleep -Seconds 2
        }
        & sc.exe stop $name 2>&1 | Out-Null
        Start-Sleep -Seconds 2

        $svc.Refresh()
        if ($svc.Status -eq "Stopped") { return "PARADO_FORZADO" }
        throw "El servicio sigue en estado $($svc.Status) tras sc.exe stop + taskkill."
    } -ArgumentList $serviceName
    Write-Host "Servicio parado ($stopResult)." -ForegroundColor Green
} catch {
    Write-Host "ERROR parando servicio: $_" -ForegroundColor Red
    exit 1
}

# --- Robocopy /MIR ---------------------------------------------------
Write-Step "[2/5] Sincronizando ficheros con robocopy /MIR"
# IMPORTANTE: robocopy /XD con ruta absoluta solo aplica al ORIGEN; los
# directorios EXTRA del destino se borran igualmente con /MIR. Usar
# nombres RELATIVOS (sin path) para que coincidan a cualquier nivel,
# tanto en origen como en destino. Asi protegemos `data\` y `logs\`
# del servidor de produccion.
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
    "/MIR",
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
    Write-Host "Intentando arrancar el servicio de nuevo..." -ForegroundColor Yellow
    Try-Start-Service
    exit 1
}
Write-Host "Sincronizacion completada (robocopy exit=$rc)." -ForegroundColor Green

# --- pip install -r requirements.txt --------------------------------
Write-Step "[3/5] Actualizando dependencias Python en $server"
try {
    $pipOutput = Invoke-Command -ComputerName $server -Credential $cred -ScriptBlock {
        param($venvPy, $root)
        Set-Location $root
        & $venvPy -m pip install --upgrade pip 2>&1 | Out-Null
        & $venvPy -m pip install -r "$root\requirements.txt" 2>&1
        return $LASTEXITCODE
    } -ArgumentList $venvPython, $rootRemote
    $pipExit = $pipOutput[-1]
    if ($pipExit -ne 0) {
        Write-Host "ERROR: pip install devolvio codigo $pipExit" -ForegroundColor Red
        Write-Host ($pipOutput | Out-String)
        Try-Start-Service
        exit 1
    }
    Write-Host "Dependencias actualizadas." -ForegroundColor Green
} catch {
    Write-Host "ERROR en PSRemoting hacia $server`: $_" -ForegroundColor Red
    Try-Start-Service
    exit 1
}

# --- Arrancar servicio ----------------------------------------------
Write-Step "[4/5] Arrancando servicio $serviceName"
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
    exit 1
}

# --- Verificar /health ----------------------------------------------
Write-Step "[5/5] Verificando que el backend responde"
$ok = $false
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}

if ($ok) {
    Write-Host "Backend OK en $healthUrl" -ForegroundColor Green
    Write-Host ""
    Write-Host "Despliegue terminado. Abre http://${server}:${servicePort}/ en el navegador." -ForegroundColor Green
} else {
    Write-Host "AVISO: el servicio esta arrancado pero /health no responde tras 15s." -ForegroundColor Yellow
    Write-Host "Revisa el log: \\$server\c$\apps\RegistroJornada\logs\service.log" -ForegroundColor Yellow
    exit 1
}
