# =============================================================================
# Menu interactivo de tareas habituales en RegistroJornada.
# Agrupa los scripts del proyecto por contexto (Git / Desarrollo / Produccion)
# con una descripcion breve. Los .bat son lanzadores que delegan en bash via
# WSL para Git/dev local, o en PowerShell directo para Produccion.
#
# Uso:
#   .\menu.ps1            (desde PowerShell en la raiz)
#   menu.bat              (doble-click en el Explorador)
# =============================================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# --- Config compartida con install-service.ps1 / deploy-to-server2022.ps1 ----
$ProdServer       = "192.168.1.222"
$ProdServiceName  = "registrojornada-backend"
$ProdServicePort  = 8600
$ProdRootRemote   = "C:\apps\RegistroJornada"
$ProdLogPath      = "\\$ProdServer\c$\apps\RegistroJornada\logs\service.log"
$ProdHealthUrl    = "http://${ProdServer}:${ProdServicePort}/health"
$ProdBaseUrl      = "http://${ProdServer}:${ProdServicePort}/"
$ProdCredCachePath = "$env:LOCALAPPDATA\registrojornada\deploy-credential.xml"

# ----------------------------------------------------------------------------
function Confirm-Action {
    param([string]$Message)
    Write-Host ""
    Write-Host "  AVISO: $Message" -ForegroundColor Yellow
    $r = Read-Host "  Continuar? [s/N]"
    return ($r -match '^(s|si|y|yes)$')
}

function Get-ProdCredential {
    if (Test-Path $ProdCredCachePath) {
        try { return Import-Clixml -Path $ProdCredCachePath } catch { }
    }
    Write-Host ""
    Write-Host "  No hay credenciales cacheadas para $ProdServer." -ForegroundColor Yellow
    Write-Host "  Lanza primero .\install-service.ps1 o .\deploy-to-server2022.ps1" -ForegroundColor DarkGray
    Write-Host "  para que se generen y guarden cifradas." -ForegroundColor DarkGray
    return $null
}

function Show-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  REGISTRO JORNADA - Menu de tareas" -ForegroundColor White
    Write-Host "  $((Get-Date).ToString('yyyy-MM-dd HH:mm'))   $env:COMPUTERNAME   prod: $ProdServer" -ForegroundColor DarkGray
    Write-Host "  -------------------------------------------------------------" -ForegroundColor DarkGray
}

function Show-Item {
    param([string]$Num, [string]$Title, [string]$Hint)
    Write-Host ("  {0,3})  " -f $Num) -NoNewline -ForegroundColor White
    Write-Host $Title.PadRight(34) -NoNewline -ForegroundColor White
    Write-Host $Hint -ForegroundColor DarkGray
}

function Show-Menu {
    Show-Header

    Write-Host ""
    Write-Host "  GIT (este repositorio)" -ForegroundColor Cyan
    Show-Item "1" "Estado del repo"           "cambios locales y diferencias con GitHub"
    Show-Item "2" "Bajar cambios"             "git pull con auto-stash"
    Show-Item "3" "Subir cambios"             "git add + commit + push"

    Write-Host ""
    Write-Host "  DESARROLLO LOCAL (este PC)" -ForegroundColor Cyan
    Show-Item "4" "Arrancar app (uvicorn)"    "python3 -m uvicorn + abre navegador local"

    Write-Host ""
    Write-Host "  PRODUCCION ($ProdServer)" -ForegroundColor Cyan
    Show-Item "5" "Desplegar cambios"         "deploy-to-server2022.ps1 (stop/sync/install/start)"
    Show-Item "6" "Estado del servicio"       "Get-Service + ping a /health"
    Show-Item "7" "Reiniciar servicio"        "stop + start con verificacion"
    Show-Item "8" "Ver log en vivo"           "tail -Wait del service.log"
    Show-Item "9" "Backup de la BBDD"         "sqlite3 .backup remoto (atomico)"
    Show-Item "10" "Abrir UI en navegador"    "$ProdBaseUrl"
    Show-Item "11" "Conectar por RDP"         "mstsc /v:$ProdServer"

    Write-Host ""
    Write-Host "  INSTALACION / AJUSTES (uso puntual)" -ForegroundColor DarkYellow
    Show-Item "12" "Instalar servicio"        "install-service.ps1 (solo primera vez)"
    Show-Item "13" "Ajustar config NSSM"      "stop rapido: TerminateProcess + KillProcessTree"

    Write-Host ""
    Write-Host "   Q)  Salir" -ForegroundColor DarkGray
    Write-Host ""
}

# ----------------------------------------------------------------------------
# Acciones de produccion
# ----------------------------------------------------------------------------
function Invoke-ProdDeploy {
    & "$PSScriptRoot\deploy-to-server2022.ps1"
}

function Invoke-ProdInstall {
    if (-not (Confirm-Action "Vas a (re)instalar el servicio en $ProdServer. Solo deberia hacerse la primera vez.")) {
        return
    }
    & "$PSScriptRoot\install-service.ps1"
}

function Invoke-ProdStatus {
    $cred = Get-ProdCredential
    if (-not $cred) { return }

    Write-Host ""
    Write-Host "  Servicio Windows en $ProdServer..." -ForegroundColor Cyan
    try {
        $status = Invoke-Command -ComputerName $ProdServer -Credential $cred -ScriptBlock {
            param($name)
            (Get-Service -Name $name).Status.ToString()
        } -ArgumentList $ProdServiceName
        $color = if ($status -eq "Running") { "Green" } else { "Yellow" }
        Write-Host ("    Estado: {0}" -f $status) -ForegroundColor $color
        Write-Host ("    Nombre: {0}" -f $ProdServiceName) -ForegroundColor DarkGray
    } catch {
        Write-Host "    ERROR consultando el servicio: $_" -ForegroundColor Red
        return
    }

    Write-Host ""
    Write-Host "  Endpoint /health..." -ForegroundColor Cyan
    try {
        $r = Invoke-WebRequest -Uri $ProdHealthUrl -UseBasicParsing -TimeoutSec 5
        Write-Host ("    HTTP {0}  {1}" -f $r.StatusCode, $r.Content) -ForegroundColor Green
    } catch {
        Write-Host ("    NO responde: {0}" -f $_.Exception.Message) -ForegroundColor Red
    }
}

$ProdStopServiceBlock = {
    # Estrategia de parada escalonada SIN bloquear el cliente:
    #   1. sc.exe stop (envia STOP al SCM y retorna inmediatamente).
    #   2. Si en 5s no para, taskkill /T /F sobre el PID raiz del servicio
    #      (nssm.exe) que mata todo el arbol descendiente (uvicorn incluido).
    #   3. sc.exe stop otra vez para resetear el SCM si quedo en STOP_PENDING.
    # NO usamos Stop-Service: bloquea hasta 30s ignorando -ErrorAction Stop.
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

    # Plan B: matar el arbol de procesos del servicio
    $wmi = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue
    $rootPid = if ($wmi) { [int]$wmi.ProcessId } else { 0 }
    if ($rootPid -gt 0) {
        & taskkill.exe /PID $rootPid /T /F 2>&1 | Out-Null
        Start-Sleep -Seconds 2
    }

    # Plan C: sc.exe stop otra vez para forzar la transicion a Stopped
    & sc.exe stop $name 2>&1 | Out-Null
    Start-Sleep -Seconds 2

    $svc.Refresh()
    if ($svc.Status -eq "Stopped") { return "PARADO_FORZADO" }
    throw "El servicio sigue en estado $($svc.Status) tras sc.exe stop + taskkill."
}

$ProdStartServiceBlock = {
    param($name)
    Start-Service -Name $name -ErrorAction Stop
    $svc = Get-Service -Name $name
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        $svc.Refresh()
        if ($svc.Status -eq "Running") { break }
    }
    if ($svc.Status -ne "Running") {
        throw "El servicio no arranco en 15s (estado: $($svc.Status))."
    }
}

function Invoke-ProdRestart {
    if (-not (Confirm-Action "Vas a reiniciar el servicio $ProdServiceName en $ProdServer.")) {
        return
    }
    $cred = Get-ProdCredential
    if (-not $cred) { return }

    try {
        Write-Host ""
        Write-Host "  Parando servicio..." -ForegroundColor Cyan
        $stopResult = Invoke-Command -ComputerName $ProdServer -Credential $cred `
            -ScriptBlock $ProdStopServiceBlock -ArgumentList $ProdServiceName
        Write-Host "  Servicio parado ($stopResult)." -ForegroundColor Green

        Write-Host "  Arrancando servicio..." -ForegroundColor Cyan
        Invoke-Command -ComputerName $ProdServer -Credential $cred `
            -ScriptBlock $ProdStartServiceBlock -ArgumentList $ProdServiceName | Out-Null
        Write-Host "  Servicio arrancado." -ForegroundColor Green
    } catch {
        Write-Host "  ERROR durante el reinicio: $_" -ForegroundColor Red
        return
    }
    Start-Sleep -Seconds 2
    Invoke-ProdStatus
}

function Invoke-ProdTailLog {
    if (-not (Test-Path $ProdLogPath)) {
        Write-Host "  ERROR: no se puede acceder a $ProdLogPath" -ForegroundColor Red
        return
    }
    Write-Host ""
    Write-Host "  Tail en vivo de $ProdLogPath" -ForegroundColor Cyan
    Write-Host "  (Pulsa Ctrl+C para salir del tail y volver al menu)" -ForegroundColor DarkGray
    Write-Host ""
    try {
        Get-Content $ProdLogPath -Tail 30 -Wait
    } catch {
        # Ctrl+C lanza excepcion; la ignoramos para volver al menu limpio.
    }
}

function Invoke-ProdBackup {
    $cred = Get-ProdCredential
    if (-not $cred) { return }

    Write-Host ""
    $defaultDir = "C:\backups\registrojornada"
    $dirInput = Read-Host "  Directorio destino en el server [$defaultDir]"
    if ([string]::IsNullOrWhiteSpace($dirInput)) { $dirInput = $defaultDir }

    Write-Host "  Lanzando backup atomico en $ProdServer..." -ForegroundColor Cyan
    $pyScript = @"
import sqlite3, datetime, pathlib
ts  = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
dst = pathlib.Path(r'__DIR__') / f'registro-{ts}.db'
dst.parent.mkdir(parents=True, exist_ok=True)
src = sqlite3.connect(r'C:\apps\RegistroJornada\data\registro.db')
bak = sqlite3.connect(str(dst))
src.backup(bak)
src.close(); bak.close()
print('OK:', dst, dst.stat().st_size, 'bytes')
"@
    $pyScript = $pyScript.Replace("__DIR__", $dirInput)

    try {
        $out = Invoke-Command -ComputerName $ProdServer -Credential $cred -ScriptBlock {
            param($py, $script)
            $tmp = New-TemporaryFile
            [System.IO.File]::WriteAllText($tmp.FullName, $script, (New-Object System.Text.UTF8Encoding $false))
            try {
                & $py $tmp.FullName 2>&1
            } finally {
                Remove-Item $tmp.FullName -Force -ErrorAction SilentlyContinue
            }
        } -ArgumentList "$ProdRootRemote\.venv\Scripts\python.exe", $pyScript
        Write-Host ($out | Out-String) -ForegroundColor Green
    } catch {
        Write-Host "  ERROR ejecutando backup: $_" -ForegroundColor Red
    }
}

function Invoke-ProdOpenUI {
    Write-Host "  Abriendo $ProdBaseUrl ..." -ForegroundColor Cyan
    Start-Process $ProdBaseUrl
}

function Invoke-ProdRdp {
    Write-Host "  Lanzando mstsc /v:$ProdServer ..." -ForegroundColor Cyan
    Start-Process mstsc -ArgumentList "/v:$ProdServer"
}

function Invoke-ProdTuneNssm {
    # Configura el servicio NSSM para que el stop sea rapido:
    #   - AppStopMethodSkip 6 (bitmask Console+Window+Threads): NSSM no envia
    #     CTRL_C ni WM_CLOSE ni WM_QUIT, va directo a TerminateProcess.
    #   - AppKillProcessTree 1: al hacer Terminate, mata todo el arbol
    #     (nssm -> python -> uvicorn) en una sola operacion.
    # Idempotente. Aplica sin necesidad de reiniciar el servicio, pero el
    # efecto se nota a partir del siguiente stop.
    $cred = Get-ProdCredential
    if (-not $cred) { return }

    Write-Host ""
    Write-Host "  Aplicando config NSSM a $ProdServiceName en $ProdServer..." -ForegroundColor Cyan
    try {
        $out = Invoke-Command -ComputerName $ProdServer -Credential $cred -ScriptBlock {
            param($name)
            $nssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
            if (-not $nssm) {
                foreach ($p in @(
                    "C:\Windows\System32\nssm.exe",
                    "C:\ProgramData\chocolatey\bin\nssm.exe",
                    "C:\Tools\nssm\nssm.exe"
                )) { if (Test-Path $p) { $nssm = $p; break } }
            }
            if (-not $nssm) { throw "NSSM no encontrado en PATH ni en rutas conocidas." }

            & $nssm set $name AppStopMethodSkip 6 | Out-String
            & $nssm set $name AppKillProcessTree 1 | Out-String

            # Confirmacion: leer y devolver los valores actuales.
            $skip = (& $nssm get $name AppStopMethodSkip).Trim()
            $tree = (& $nssm get $name AppKillProcessTree).Trim()
            return "AppStopMethodSkip=$skip  AppKillProcessTree=$tree"
        } -ArgumentList $ProdServiceName
        Write-Host "  $out" -ForegroundColor Green
        Write-Host "  Listo. El proximo stop sera limpio (PARADO_NORMAL en ~1s)." -ForegroundColor DarkGray
    } catch {
        Write-Host "  ERROR ajustando NSSM: $_" -ForegroundColor Red
    }
}

# ----------------------------------------------------------------------------
# Loop principal
# ----------------------------------------------------------------------------
while ($true) {
    Show-Menu
    $choice = (Read-Host "  Opcion").Trim().ToLower()
    Write-Host ""

    $cmd = $null

    switch -Regex ($choice) {
        '^(1)$'  { $cmd = { & "$PSScriptRoot\estado.bat" } }
        '^(2)$'  { $cmd = { & "$PSScriptRoot\bajar.bat" } }
        '^(3)$'  { $cmd = { & "$PSScriptRoot\subir.bat" } }
        '^(4)$'  { $cmd = { & "$PSScriptRoot\start.bat" } }
        '^(5)$'  { $cmd = { Invoke-ProdDeploy } }
        '^(6)$'  { $cmd = { Invoke-ProdStatus } }
        '^(7)$'  { $cmd = { Invoke-ProdRestart } }
        '^(8)$'  { $cmd = { Invoke-ProdTailLog } }
        '^(9)$'  { $cmd = { Invoke-ProdBackup } }
        '^(10)$' { $cmd = { Invoke-ProdOpenUI } }
        '^(11)$' { $cmd = { Invoke-ProdRdp } }
        '^(12)$' { $cmd = { Invoke-ProdInstall } }
        '^(13)$' { $cmd = { Invoke-ProdTuneNssm } }
        '^(q|0|exit|salir)$' { exit 0 }
        default {
            Write-Host "  Opcion no reconocida." -ForegroundColor Yellow
            Start-Sleep -Seconds 1
            continue
        }
    }

    if ($cmd) {
        try {
            & $cmd
        } catch {
            Write-Host ""
            Write-Host "  ERROR: $($_.Exception.Message)" -ForegroundColor Red
        }
        Write-Host ""
        Read-Host "  --- Pulsa Enter para volver al menu ---" | Out-Null
    }
}
