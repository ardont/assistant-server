# -*- coding: utf-8 -*-
import os
import sys
import time
import zipfile
import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

print("=" * 50)
print("💾 Запуск Резервного Копирования HomeServer")
print("=" * 50)

base_dir = Path("C:/HomeServer")
backup_dir = base_dir / "backups"
backup_dir.mkdir(parents=True, exist_ok=True)

ts_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
zip_path = backup_dir / f"homeserver_backup_{ts_str}.zip"

sources = [base_dir / "data", base_dir / "config", base_dir / "inbox_proposals.json"]

print(f"Целевой архив: {zip_path.name}")
total_files = 0
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for src in sources:
        if not src.exists():
            continue
        if src.is_file():
            zf.write(src, arcname=src.name)
            total_files += 1
            print(f"➕ Добавлен файл: {src.name}")
            time.sleep(0.3)
        elif src.is_dir():
            for p in src.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(base_dir)
                    zf.write(p, arcname=str(rel))
                    total_files += 1
                    print(f"➕ Добавлен файл: {rel}")
                    time.sleep(0.2)

size_mb = round(zip_path.stat().st_size / (1024 * 1024), 2)
print("=" * 50)
print(f"✅ Резервное копирование успешно завершено!")
print(f"📦 Всего сохранено файлов: {total_files}")
print(f"📊 Размер архива: {size_mb} MB")
print(f"[METRIC:backup_size={size_mb} MB]")
print(f"[METRIC:backup_files={total_files}]")
print(f"[METRIC:backup_time={datetime.datetime.now().strftime('%H:%M:%S')}]")
print("=" * 50)
