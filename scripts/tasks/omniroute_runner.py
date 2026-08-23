# -*- coding: utf-8 -*-
"""
OmniRoute AI Gateway Runner for HomeServer
Launches local OmniRoute proxy on port 20128 for free tokens & multi-provider aggregation.
"""
import os
import sys
import subprocess
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

OMNIR_CMD = Path(os.environ.get("APPDATA", "")) / "npm" / "omniroute.cmd"
if not OMNIR_CMD.exists():
    OMNIR_CMD = "omniroute"

def main():
    print("=" * 60)
    print("🚀 Запуск OmniRoute Local AI Gateway (Порт 20128)")
    print("=" * 60)
    print("🌐 Панель управления OmniRoute:  http://localhost:20128")
    print("📡 OpenAI эндпоинт для запросов: http://localhost:20128/v1")
    print("=" * 60)
    
    cmd = [str(OMNIR_CMD), "serve", "--port", "20128"]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        for line in iter(proc.stdout.readline, ''):
            if line:
                print(line.rstrip())
        proc.wait()
    except Exception as e:
        print(f"[!] Ошибка запуска OmniRoute: {e}")

if __name__ == "__main__":
    main()
