@echo off
chcp 65001 >nul
title Активация RDP и установка пароля
color 0A

:: Проверка прав администратора
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ==============================================================================
    echo  Запрос прав Администратора для включения службы RDP и установки пароля...
    echo ==============================================================================
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ==============================================================================
echo              🚀 Включение RDP и настройка пароля 1234
echo ==============================================================================
echo.

echo [1/5] Установка пароля 1234 для пользователя %USERNAME%...
net user "%USERNAME%" 1234 >nul 2>&1

echo [2/5] Включение RDP в реестре Windows...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f >nul

echo [3/5] Настройка проверки подлинности (NLA)...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" /v UserAuthentication /t REG_DWORD /d 1 /f >nul

echo [4/5] Запуск и автозагрузка службы TermService...
sc config TermService start= auto >nul
net start TermService >nul 2>&1

echo [5/5] Разрешение RDP (порт 3389) в Брандмауэре Windows...
netsh advfirewall firewall set rule group="remote desktop" new enable=Yes >nul 2>&1
netsh advfirewall firewall set rule group="дистанционное управление рабочим столом" new enable=Yes >nul 2>&1
powershell -Command "Enable-NetFirewallRule -DisplayGroup 'Remote Desktop' -ErrorAction SilentlyContinue; Enable-NetFirewallRule -DisplayGroup 'Дистанционное управление рабочим столом' -ErrorAction SilentlyContinue" >nul 2>&1

echo.
echo ==============================================================================
echo [✓] RDP УСПЕШНО НАСТРОЕН!
echo.
echo Параметры подключения:
echo   - IP (Wi-Fi):     192.168.50.108
echo   - IP (Tailscale): 100.110.6.52
echo   - Пользователь:   %USERNAME%
echo   - Пароль:         1234
echo ==============================================================================
echo.
timeout /t 3 >nul
exit /b 0
