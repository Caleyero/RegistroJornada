@echo off
REM Atajo directo: tail en vivo del log de produccion.
REM Equivale a la opcion 8 del menu.bat. Pulsa Ctrl+C para salir.
title RegistroJornada - Log produccion (Ctrl+C para salir)
powershell.exe -ExecutionPolicy Bypass -NoProfile -Command ^
  "$p='\\192.168.1.222\c$\apps\RegistroJornada\logs\service.log';" ^
  "if (-not (Test-Path $p)) { Write-Host 'No accesible:' $p -ForegroundColor Red; exit 1 };" ^
  "Get-Content $p -Tail 30 -Wait"
