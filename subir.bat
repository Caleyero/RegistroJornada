@echo off
chcp 65001 >nul
title RegistroJornada - Subir cambios
for /f "usebackq tokens=*" %%i in (`wsl -d Ubuntu -e wslpath -a "%~dp0."`) do set "WSL_DIR=%%i"
wsl -d Ubuntu -e bash -lc "cd '%WSL_DIR%' && bash scripts/devops/git-subir.sh"
echo.
pause
