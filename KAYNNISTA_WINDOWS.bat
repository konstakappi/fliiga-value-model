@echo off
setlocal
cd /d "%~dp0"
title F-liiga vedonlyontiapuri - pida tama ikkuna auki

echo.
echo ========================================
echo   F-liiga vedonlyontiapuri
echo ========================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo Pythonia ei loytynyt.
    echo Asenna Python 3.11 tai uudempi osoitteesta https://www.python.org/downloads/
    echo Valitse asennuksessa "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Ensimmainen kaynnistys: luodaan ohjelmalle oma ymparisto...
    py -3 -m venv .venv
    if errorlevel 1 goto :error
)

echo Tarkistetaan tarvittavat paketit...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -q -e ".[app]"
if errorlevel 1 goto :error

echo Kaynnistetaan sovellus selaimeen...
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://localhost:8501'"
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true
exit /b 0

:error
echo.
echo Asennus tai kaynnistys epaonnistui. Kopioi virheilmoitus talteen.
pause
exit /b 1
