@echo off
chcp 65001 >nul
title Registros de Jornada - Arrancar

REM Resuelve la ruta WSL de esta carpeta para que funcione donde sea que la clones.
for /f "usebackq tokens=*" %%i in (`wsl -d Ubuntu -e wslpath -a "%~dp0."`) do set "WSL_DIR=%%i"

echo Arrancando la app en http://127.0.0.1:8600/ ...
echo (Cierra esta ventana o pulsa Ctrl+C para parar.)
echo.

REM Abre el navegador en cuanto la app responda
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8600/"

wsl -d Ubuntu -e bash -lc "cd '%WSL_DIR%' && bash run.sh"
pause
