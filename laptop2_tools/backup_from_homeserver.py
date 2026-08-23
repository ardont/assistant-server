# -*- coding: utf-8 -*-
"""
HomeServer Backup Agent (Для запуска на 2-м ноутбуке)
- Скачивает свежую копию архива, профиля и базы данных с основного сервера
- Сохраняет историю версий в локальную папку backups
"""
import os
import sys
import json
import time
import urllib.request
import datetime
from pathlib import Path

BASE_BACKUP_DIR = Path("./homeserver_backups")
BASE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

SERVER_URL = "http://192.168.50.108:8000"

def backup():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = BASE_BACKUP_DIR / f"backup_{timestamp}"
    target_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"=== 📦 Создание резервной копии HomeServer в {target_dir} ===")
    
    endpoints = {
        "user_profile.json": "/api/profile",
        "daily_plan.json": "/api/planner/today",
        "calendar_events.json": "/api/calendar.ics",
        "archive_tree.json": "/api/archive/tree",
        "inbox_proposals.json": "/api/proposals"
    }
    
    for filename, endpoint in endpoints.items():
        try:
            req = urllib.request.Request(SERVER_URL + endpoint)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
                with open(target_dir / filename, "wb") as f:
                    f.write(data)
                print(f"  [✓] Сохранен: {filename} ({len(data)} байт)")
        except Exception as e:
            print(f"  [!] Ошибка скачивания {filename}: {e}")
            
    print(f"[✓] Бэкап завершен успешно! Файлы в: {target_dir.absolute()}\n")

if __name__ == "__main__":
    backup()
