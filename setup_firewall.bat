@echo off
chcp 65001 >nul
echo [1/2] Setting up Windows Firewall rules for HomeServer...
netsh advfirewall firewall delete rule name="HomeServer Web Port 8000" >nul 2>&1
netsh advfirewall firewall add rule name="HomeServer Web Port 8000" dir=in action=allow protocol=TCP localport=8000 profile=any >nul 2>&1

netsh advfirewall firewall delete rule name="HomeServer Python" >nul 2>&1
netsh advfirewall firewall add rule name="HomeServer Python" dir=in action=allow program="C:\HomeServer\venv\Scripts\python.exe" profile=any >nul 2>&1

echo [2/2] Checking rule status...
netsh advfirewall firewall show rule name="HomeServer Web Port 8000"
echo.
echo [+] Windows Firewall configured successfully!
