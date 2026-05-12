# =============================================================================
# Menu interactivo de tareas habituales en RegistroJornada.
# Agrupa los scripts del proyecto por contexto (Git / Desarrollo local) con
# una descripcion breve. Los .bat son lanzadores que delegan en bash via WSL.
#
# Uso:
#   .\menu.ps1            (desde PowerShell en la raiz)
#   menu.bat              (doble-click en el Explorador)
# =============================================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Confirm-Action {
    param([string]$Message)
    Write-Host ""
    Write-Host "  AVISO: $Message" -ForegroundColor Yellow
    $r = Read-Host "  Continuar? [s/N]"
    return ($r -match '^(s|si|y|yes)$')
}

function Show-Header {
    Clear-Host
    Write-Host ""
    Write-Host "  REGISTRO JORNADA - Menu de tareas" -ForegroundColor White
    Write-Host "  $((Get-Date).ToString('yyyy-MM-dd HH:mm'))   $env:COMPUTERNAME" -ForegroundColor DarkGray
    Write-Host "  -------------------------------------------------------------" -ForegroundColor DarkGray
}

function Show-Item {
    param([string]$Num, [string]$Title, [string]$Hint)
    Write-Host ("  {0,3})  " -f $Num) -NoNewline -ForegroundColor White
    Write-Host $Title.PadRight(36) -NoNewline -ForegroundColor White
    Write-Host $Hint -ForegroundColor DarkGray
}

function Show-Menu {
    Show-Header

    Write-Host ""
    Write-Host "  GIT (este repositorio)" -ForegroundColor Cyan
    Show-Item "1" "Estado del repo"           "estado.bat - cambios locales y diferencias con GitHub"
    Show-Item "2" "Bajar cambios"             "bajar.bat  - git pull con auto-stash"
    Show-Item "3" "Subir cambios"             "subir.bat  - git add + commit + push"

    Write-Host ""
    Write-Host "  DESARROLLO LOCAL (este PC)" -ForegroundColor Cyan
    Show-Item "4" "Arrancar app (uvicorn)"    "start.bat  - python3 -m uvicorn + abrir navegador"

    Write-Host ""
    Write-Host "   Q)  Salir" -ForegroundColor DarkGray
    Write-Host ""
}

while ($true) {
    Show-Menu
    $choice = (Read-Host "  Opcion").Trim().ToLower()
    Write-Host ""

    $cmd = $null
    $needsConfirm = $null

    switch -Regex ($choice) {
        '^(1)$'  { $cmd = { & "$PSScriptRoot\estado.bat" } }
        '^(2)$'  { $cmd = { & "$PSScriptRoot\bajar.bat" } }
        '^(3)$'  { $cmd = { & "$PSScriptRoot\subir.bat" } }
        '^(4)$'  { $cmd = { & "$PSScriptRoot\start.bat" } }
        '^(q|0|exit|salir)$' { exit 0 }
        default {
            Write-Host "  Opcion no reconocida." -ForegroundColor Yellow
            Start-Sleep -Seconds 1
            continue
        }
    }

    if ($needsConfirm) {
        if (-not (Confirm-Action $needsConfirm)) {
            Write-Host "  Cancelado." -ForegroundColor DarkGray
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
