@echo off
chcp 65001 >nul
title Registros de Jornada - Arrancar
cd /d "%~dp0"

REM === 1) Preferir entorno virtual local .venv (Windows nativo) ============
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
    if not exist ".env" copy .env.example .env >nul
    echo Arrancando con .venv en http://127.0.0.1:8600/ ...
    echo (Cierra esta ventana o pulsa Ctrl+C para parar.)
    echo.
    start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8600/"
    python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8600
    pause
    exit /b
)

REM === 2) Si no hay venv, probar WSL Ubuntu (modo Linux) ====================
where wsl >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: No hay .venv y WSL tampoco esta disponible.
    echo Ejecuta primero setup.bat para crear un entorno virtual local.
    pause
    exit /b 1
)

for /f "usebackq tokens=*" %%i in (`wsl -d Ubuntu -e wslpath -a "%~dp0."`) do set "WSL_DIR=%%i"
if "%WSL_DIR%"=="" (
    echo.
    echo ERROR: No se pudo determinar la ruta WSL del proyecto.
    echo Ejecuta primero setup.bat para crear un entorno virtual local.
    pause
    exit /b 1
)

echo Arrancando con WSL Ubuntu en http://127.0.0.1:8600/ ...
echo (Cierra esta ventana o pulsa Ctrl+C para parar.)
echo.
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:8600/"
wsl -d Ubuntu -e bash -lc "cd '%WSL_DIR%' && bash run.sh"
pause
