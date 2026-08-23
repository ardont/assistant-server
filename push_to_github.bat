@echo off
chcp 65001 >nul
title Отправка проекта на GitHub (ardont/assistant-server)
echo ================================================================================
echo           🚀 Публикация репозитория на GitHub (assistant-server)
echo ================================================================================

cd /d "C:\HomeServer"

echo [*] Проверка Git репозитория...
tools\git\cmd\git.exe status

echo.
echo [*] Выполняется отправка в репозиторий https://github.com/ardont/assistant-server.git...
echo [*] Если откроется окно авторизации GitHub в браузере, подтвердите вход (Authorize).
echo.

tools\git\cmd\git.exe push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ================================================================================
    echo  ✅ ПРОЕКТ УСПЕШНО ОПУБЛИКОВАН НА GITHUB:
    echo     https://github.com/ardont/assistant-server
    echo ================================================================================
) else (
    echo ================================================================================
    echo  ⚠️ Требуется авторизация GitHub (вход через браузер или Personal Access Token).
    echo ================================================================================
)

pause
