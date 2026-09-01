@echo off
REM avvia_gui.bat — Avviatore per Windows
REM Doppio click per aprire l'interfaccia grafica
title Real Estate Monitor
echo.
echo  ======================================
echo    Real Estate Monitor - Avvio GUI
echo  ======================================
echo.
REM Attiva il virtualenv del progetto
call "%~dp0.venv\Scripts\activate.bat"
REM Controlla se Python è disponibile
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERRORE: Python non trovato nel PATH.
    echo Scarica Python da: https://www.python.org/downloads/
    pause
    exit /b 1
)
REM Avvia l'applicazione
python "%~dp0main.py" --gui
if %errorlevel% neq 0 (
    echo.
    echo ERRORE durante l'avvio. Esegui prima: python setup.py
    pause
)
