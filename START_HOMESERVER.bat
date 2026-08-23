@echo off
chcp 65001 >nul
title HomeServer Multi-Channel AI Hub 24/7
echo ================================================================================
echo           🚀 Запуск HomeServer Multi-Channel AI Hub 24/7
echo ================================================================================

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [!] Виртуальное окружение venv не найдено. Создание...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

if not exist "config\.env" (
    if exist ".env.example" (
        echo [*] Копирование .env.example в config\.env...
        mkdir config 2>nul
        copy .env.example config\.env >nul
        echo [!] Пожалуйста, укажите свои API ключи в config\.env
    )
)

echo [*] Запуск сервера и всех фоновых служб...
python scripts\main.py

pause
