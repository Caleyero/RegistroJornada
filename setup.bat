@echo off
chcp 65001 >nul
title Registros de Jornada - Setup (entorno virtual)
cd /d "%~dp0"

echo ============================================
echo   Setup de RegistroJornada
echo ============================================
echo.

REM --- 1. Verificar Python ---
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: No se encuentra "python" en el PATH.
    echo Instala Python 3.10+ desde https://www.python.org/downloads/
    echo y marca "Add python to PATH" durante la instalacion.
    pause
    exit /b 1
)

REM --- 2. Crear entorno virtual ---
if not exist ".venv" (
    echo Creando entorno virtual en .venv\ ...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR al crear el entorno virtual.
        pause
        exit /b 1
    )
) else (
    echo .venv ya existe — actualizando dependencias.
)

REM --- 3. Activar e instalar ---
call ".venv\Scripts\activate.bat"
echo.
echo Actualizando pip...
python -m pip install --upgrade pip --disable-pip-version-check

echo.
echo Instalando dependencias de requirements.txt...
pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo ERROR al instalar dependencias.
    pause
    exit /b 1
)

REM --- 4. Crear .env si no existe ---
if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo .env creado a partir de .env.example
)

echo.
echo ============================================
echo   OK — entorno listo.
echo   Ahora puedes hacer doble-click en start.bat
echo ============================================
pause
