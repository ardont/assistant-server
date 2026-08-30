@echo off
title HomeServer 24/7 AI Hub
echo =========================================
echo Starting HomeServer ...
echo =========================================
cd /d %~dp0

echo Проверка и настройка Everywhere AI...
powershell -ExecutionPolicy Bypass -File setup_everywhere.ps1
if exist "Everywhere\Everywhere.exe" (
    echo Запуск Everywhere AI в фоновом режиме...
    start "" "Everywhere\Everywhere.exe"
)

call venv\Scripts\activate.bat
python scripts\web_server.py
pause
