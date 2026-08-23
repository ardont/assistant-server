# -*- coding: utf-8 -*-
"""
Cloudflare Tunnel Runner for HomeServer (Self-Healing Auto-Reconnect)
Automatically manages cloudflared.exe, restarts on edge dropouts, and provisions a secure HTTPS URL.
"""
import os
import sys
import json
import time
import re
import subprocess
import urllib.request
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
TOOLS_DIR = BASE_DIR / "tools"
CONFIG_DIR = BASE_DIR / "config"
STATUS_FILE = CONFIG_DIR / "tunnel_status.json"
CLOUDFLARED_EXE = TOOLS_DIR / "cloudflared.exe"

CLOUDFLARED_DOWNLOAD_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

def ensure_cloudflared_installed() -> bool:
    if CLOUDFLARED_EXE.exists() and CLOUDFLARED_EXE.stat().st_size > 1000000:
        return True
    
    print("[Cloudflare] 📥 Скачивание официального бинарника cloudflared.exe...")
    try:
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(CLOUDFLARED_DOWNLOAD_URL, str(CLOUDFLARED_EXE))
        print(f"[Cloudflare] [+] cloudflared.exe успешно установлен: {CLOUDFLARED_EXE}")
        return True
    except Exception as e:
        print(f"[Cloudflare] [!] Не удалось автоматически скачать cloudflared: {e}")
        return False

def save_tunnel_status(url: str, active: bool):
    try:
        STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "active": active,
            "url": url,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        STATUS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[Cloudflare] Ошибка записи статуса: {e}")

def run_cloudflare_tunnel_loop(local_port: int = 8000):
    if not ensure_cloudflared_installed():
        print("[Cloudflare] Пропуск запуска туннеля (cloudflared.exe отсутствует)")
        return

    while True:
        print(f"[Cloudflare] 🚀 Запуск защищенного HTTPS туннеля к http://localhost:{local_port}...")
        save_tunnel_status("", False)
        
        cmd = [
            str(CLOUDFLARED_EXE),
            "tunnel",
            "--url", f"http://localhost:{local_port}",
            "--no-autoupdate"
        ]

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )

            tunnel_url = ""
            url_regex = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

            for line in iter(proc.stdout.readline, ""):
                match = url_regex.search(line)
                if match:
                    tunnel_url = match.group(0)
                    print("=" * 72)
                    print(f"🌐 [CLOUDFLARE HTTPS TUNNEL АКТИВЕН]: {tunnel_url}")
                    print(f"📱 VK Mini App: {tunnel_url}/vk-app")
                    print("=" * 72)
                    save_tunnel_status(tunnel_url, True)
                    
                    # Also notify via ntfy
                    try:
                        from core.notifier import send_push
                        send_push("🌐 Cloudflare HTTPS готов", f"Новый адрес доступа:\n{tunnel_url}\nVK Mini App: {tunnel_url}/vk-app", tags="globe")
                    except Exception:
                        pass
                    break

            # Monitor process until termination or disconnect
            proc.wait()
            print("[Cloudflare] ⚠️ Туннель завершил работу. Автоматический перезапуск через 5 сек...")
            save_tunnel_status("", False)
            time.sleep(5)

        except Exception as e:
            print(f"[Cloudflare] Ошибка туннеля: {e}. Перезапуск через 10 сек...")
            save_tunnel_status("", False)
            time.sleep(10)

def start_cloudflare_thread(local_port: int = 8000):
    t = threading.Thread(target=run_cloudflare_tunnel_loop, args=(local_port,), daemon=True, name="CloudflareTunnelThread")
    t.start()
    return t

if __name__ == "__main__":
    run_cloudflare_tunnel_loop()
