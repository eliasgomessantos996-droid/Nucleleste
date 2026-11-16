@echo off
setlocal
title Sistema de Recepcao - Nucleleste
cd /d "%~dp0"

set "VENV=%LOCALAPPDATA%\SistemaNucleleste\venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Preparando o sistema pela primeira vez neste computador...
    where py >nul 2>nul && (py -3 -m venv "%VENV%") || (python -m venv "%VENV%")
    if not exist "%VENV%\Scripts\python.exe" (
        echo.
        echo ERRO: Python nao encontrado. Instale o Python 3 em https://www.python.org/downloads/
        echo marcando a opcao "Add python.exe to PATH" e rode este arquivo de novo.
        pause
        exit /b 1
    )
)

"%VENV%\Scripts\python.exe" -c "import flask, waitress" >nul 2>nul || (
    echo Instalando componentes necessarios...
    "%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
)

start "" cmd /c "timeout /t 3 >nul & start http://localhost:8080"
"%VENV%\Scripts\python.exe" servidor.py
pause
