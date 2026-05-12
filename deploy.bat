@echo off
REM Atajo directo: despliega los cambios del repo al servidor de produccion.
REM Equivale a la opcion 5 del menu.bat.
title RegistroJornada - Deploy a produccion
powershell.exe -ExecutionPolicy Bypass -NoProfile -File "%~dp0deploy-to-server2022.ps1"
echo.
pause
