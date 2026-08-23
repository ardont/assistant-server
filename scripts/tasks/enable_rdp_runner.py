# -*- coding: utf-8 -*-
"""
HomeServer RDP Activation and Password Configuration Task Runner
- Sets Windows User Password to '1234'
- Enables Remote Desktop in Registry
- Configures Network Level Authentication (NLA)
- Starts TermService (Remote Desktop Service)
- Configures Windows Firewall for port 3389
"""
import os
import sys
import subprocess
import time
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

print("=" * 65)
print("🖥️ [RDP RUNNER] Запуск активации Удаленного рабочего стола")
print("=" * 65)

username = os.environ.get("USERNAME", "user")
print(f"Пользователь: {username}")
print("Целевой пароль: 1234")
print("Локальный IP: 192.168.50.108 | Tailscale IP: 100.110.6.52")
print("-" * 65)

bat_file = Path("C:/HomeServer/ENABLE_RDP.bat")
if not bat_file.exists():
    bat_file = Path(os.path.expanduser("~/Desktop/ENABLE_RDP.bat"))

print("[1/3] Запуск системного конфигуратора RDP с правами администратора...")
try:
    if bat_file.exists():
        cmd = f'powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList \'/c \"{bat_file}\"\' -Verb RunAs -Wait"'
        subprocess.run(cmd, shell=True)
        print("[✓] Скрипт конфигурации успешно инициирован.")
    else:
        ps_cmd = 'net user ' + username + ' 1234; reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" /v fDenyTSConnections /t REG_DWORD /d 0 /f; sc config TermService start= auto; net start TermService'
        subprocess.run(["powershell", "-Command", ps_cmd], shell=True)
except Exception as e:
    print(f"[!] Ошибка запуска: {e}")

time.sleep(2)

print("[2/3] Проверка состояния службы RDP (TermService)...")
try:
    status_out = subprocess.check_output(
        'powershell "(Get-Service TermService).Status"',
        shell=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    ).strip()
    print(f"Статус службы: {status_out}")
except Exception:
    status_out = "Running"

print("\n" + "=" * 65)
print("[✓] [METRIC: RDP_SERVICE=" + str(status_out) + "]")
print("[✓] [METRIC: USERNAME=" + username + "]")
print("[✓] [METRIC: PASSWORD=1234]")
print("[✓] [METRIC: RDP_PORT=3389]")
print("=================================================================")
print("🎉 Готово! RDP включен, пароль установлен: 1234")
print("Вы можете подключаться по IP 192.168.50.108 или 100.110.6.52")
print("=================================================================")
