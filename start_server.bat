@echo off
chcp 65001 >nul
title HomeServer 24/7 AI Hub and Network Services
color 0B

echo ==============================================================================
echo                      🚀 HomeServer 24/7 AI Hub and Automation
echo ==============================================================================
echo.

:: 1. Настройка сетевого доступа к папке INBOX
echo [1/3] Настройка общего доступа к сетевой папке INBOX...
net share INBOX=C:\HomeServer\inbox /grant:Everyone,FULL >nul 2>&1
net share INBOX=C:\HomeServer\inbox /grant:Все,FULL >nul 2>&1
icacls "C:\HomeServer\inbox" /grant "*S-1-1-0:(OI)(CI)F" /T >nul 2>&1
echo [+] Сетевой доступ к INBOX активен: \\192.168.50.108\INBOX
echo.

:: 2. Вывод доступных адресов подключения
echo ------------------------------------------------------------------------------
echo [2/3] Доступные адреса и сервисы:
echo.
echo   - Веб-панель (этот ПК):       http://localhost:8000
echo   - Веб-панель (по Wi-Fi):      http://192.168.50.108:8000
echo   - Веб-панель (VPN Tailscale): http://100.110.6.52:8000
echo   - Сетевая папка для ноутбука: \\192.168.50.108\INBOX
echo   - Календарь (iCalendar):      http://192.168.50.108:8000/api/calendar.ics
echo   - Push-тема (ntfy):           homeserver_user_2026
echo ------------------------------------------------------------------------------
echo.

:: 3. Автоматическое открытие браузера
echo [3/3] Запуск веб-панели и фоновых сервисов ИИ...
start "" "http://localhost:8000"

:: 4. Запуск основного сервера Python FastAPI + Планировщик + Gemini AI
if exist "C:\HomeServer\venv\Scripts\python.exe" (
    "C:\HomeServer\venv\Scripts\python.exe" "C:\HomeServer\scripts\main.py"
) else (
    echo [ПРЕДУПРЕЖДЕНИЕ] Виртуальное окружение не найдено по пути C:\HomeServer\venv
    echo Попытка запуска через системный python...
    python "C:\HomeServer\scripts\main.py"
)

if %errorlevel% neq 0 (
    echo.
    echo ==============================================================================
    echo [ОШИБКА] Работа сервера была завершена или произошел сбой.
    echo ==============================================================================
    pause
)
