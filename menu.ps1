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
    Write-Host "  INSTALACION (uso unico)" -ForegroundColor DarkYellow
    Show-Item "12" "Instalar servicio"        "install-service.ps1 (solo primera vez)"

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
    Write-Host ""
    Write-Host "  Servicio Windows en $ProdServer..." -ForegroundColor Cyan
    try {
        $svc = Get-Service -ComputerName $ProdServer -Name $ProdServiceName -ErrorAction Stop
        $color = if ($svc.Status -eq "Running") { "Green" } else { "Yellow" }
        Write-Host ("    Estado: {0}" -f $svc.Status) -ForegroundColor $color
        Write-Host ("    Nombre: {0}" -f $svc.Name) -ForegroundColor DarkGray
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

function Invoke-ProdRestart {
    if (-not (Confirm-Action "Vas a reiniciar el servicio $ProdServiceName en $ProdServer.")) {
        return
    }
    Write-Host ""
    Write-Host "  Parando servicio..." -ForegroundColor Cyan
    Get-Service -ComputerName $ProdServer -Name $ProdServiceName | Stop-Service -Force
    Start-Sleep -Seconds 2
    Write-Host "  Arrancando servicio..." -ForegroundColor Cyan
    Get-Service -ComputerName $ProdServer -Name $ProdServiceName | Start-Service
    Start-Sleep -Seconds 3
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
