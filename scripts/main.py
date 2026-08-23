# -*- coding: utf-8 -*-
"""
HomeServer Main Dispatcher, Task Runner & Web Dashboard (24/7 Supervisor)
Multi-Channel Remote Hub: Web UI + Wi-Fi + Tailscale + Cloudflare HTTPS + VK Bot + MAX Bot + Telegram Bot.
"""
import time
import os
import sys
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.append(os.path.dirname(__file__))

from core.notifier import notify_info, notify_error, log_event
from core.system_status import get_status_text
from core.system_watchdog import start_watchdog_thread
from tasks.file_ai_organizer import scan_and_process_inbox
from core.vk_bot import start_vk_bot_thread
from core.max_bot import start_max_bot_thread
from core.telegram_bot import start_telegram_bot_thread
from tasks.cloudflare_runner import start_cloudflare_thread
from core.proactive_mentor import check_and_send_proactive_checkin
import schedule
import uvicorn
from web_server import app

BASE_DIR = Path("C:/HomeServer")
INBOX_DIR = BASE_DIR / "inbox"

def job_heartbeat():
    status = get_status_text()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 💓 [HEARTBEAT] Аптайм и статус:\n{status}")
    log_event("HEARTBEAT", status)

def job_check_inbox():
    try:
        scan_and_process_inbox(auto_apply=False)
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [!] Ошибка сканирования INBOX: {e}")

def run_scheduler():
    schedule.every(30).seconds.do(job_check_inbox)
    schedule.every(3).hours.do(job_heartbeat)
    schedule.every(10).minutes.do(check_and_send_proactive_checkin)
    
    # Первичная проверка при старте
    job_check_inbox()
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            notify_error("Сбой в планировщике задач", str(e))
            time.sleep(5)

def main():
    print("=" * 76)
    print("🚀 HomeServer 24/7 Multi-Channel AI Hub & Web Dashboard")
    print("=" * 76)
    print("📡 Веб-панель (этот ПК):          http://localhost:8000")
    print("📱 Веб-панель (по Wi-Fi):         http://192.168.50.108:8000")
    print("🔒 Веб-панель (Tailscale):       http://100.110.6.52:8000")
    print("📁 Папка INBOX:                   C:\\HomeServer\\inbox (\\\\192.168.50.108\\INBOX)")
    print("🤖 AI Модели:                     Gemini Flash (с ротацией) + DeepSeek + Local NLP")
    print("💬 Мессенджеры:                   VK Bot + MAX Bot + Telegram Bot (Автономные)")
    print("🛡️ Защита памяти:                 Watchdog активен (лимит 380 МБ, авто-GC каждые 60с)")
    print("=" * 76)
    print("Журнал событий сервера (логи запросов в реальном времени):\n")
    
    # 1. Запуск сторожевого пса памяти
    start_watchdog_thread()
    
    # 2. Запуск фонового планировщика
    t_sched = threading.Thread(target=run_scheduler, daemon=True, name="MainSchedulerThread")
    t_sched.start()

    # 3. Запуск ботов мессенджеров
    start_vk_bot_thread()
    start_max_bot_thread()
    start_telegram_bot_thread()

    # 4. Запуск защищенного Cloudflare Tunnel для удаленного Web-доступа без VPN
    start_cloudflare_thread(local_port=8000)
    
    # 5. Запуск Uvicorn веб-сервера
    try:
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning", access_log=False)
    except (KeyboardInterrupt, SystemExit):
        print("\nОстановка сервера...")

if __name__ == "__main__":
    main()
