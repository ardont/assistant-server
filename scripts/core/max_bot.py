import ssl
SSL_CTX = ssl._create_unverified_context()

def get_max_opener():
    proxy = os.getenv("MAX_PROXY_URL", "").strip()
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MAX_PROXY_URL="):
                    proxy = line.strip().split("=", 1)[1].strip()
    handlers = [urllib.request.HTTPSHandler(context=SSL_CTX)]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)

def sanitize_outgoing_text(text: str) -> str:
    """Удаляет из ответов локальные системные пути, внутренние IP и токены перед отправкой в VK/MAX."""
    t = str(text)
    t = re.sub(r'[a-zA-Z]:\\[hH]ome[sS]erver\\[a-zA-Z0-9_\\-]+', '[STORAGE_PATH]', t)
    t = re.sub(r'\b192\.168\.\d{1,3}\.\d{1,3}\b', '[LOCAL_IP]', t)
    t = re.sub(r'\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[VPN_IP]', t)
    t = re.sub(r'\b(?:sk-[a-zA-Z0-9_-]{20,}|AQ\.[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{20,})\b', '[PROTECTED_KEY]', t)
    return t

# -*- coding: utf-8 -*-
"""
HomeServer MAX Messenger Bot Integration
Connects to official MAX Bot API (platform-api2.max.ru / max-botapi-python).
"""
import os
import sys
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import threading
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
CONFIG_PATH = BASE_DIR / "config" / ".env"
INBOX_DIR = BASE_DIR / "inbox"
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.append(str(SCRIPTS_DIR))

from core.chat_agent import ask_chat_agent
from core.audio_transcriber import transcribe_audio_file
from core.study_planner import load_daily_plan
from core.system_status import get_status_text

MAX_API_BASE = "https://platform-api2.max.ru"

def get_max_config():
    token = os.getenv("MAX_BOT_TOKEN", "")
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MAX_BOT_TOKEN="):
                    token = line.strip().split("=", 1)[1]
    return token.strip()

def max_api_call(endpoint: str, data: dict = None, token: str = "") -> dict:
    url = f"{MAX_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "HomeServer-MAX-Bot/1.0"
    }
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers)
    opener = get_max_opener()
    try:
        with opener.open(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def send_max_message(chat_id: str, text: str, token: str):
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    max_api_call("/api/v1/messages/send", payload, token)

def run_max_bot_polling():
    token = get_max_config()
    if not token:
        print("[MAX Bot] ⚪ MAX_BOT_TOKEN не задан в .env. Бот MAX в режиме ожидания токена.")
        return

    print("[MAX Bot] 🟢 Запуск MAX Bot Polling...")
    last_event_id = None
    
    while True:
        try:
            token = get_max_config()
            if not token:
                time.sleep(10)
                continue

            params = f"?last_id={last_event_id}" if last_event_id else ""
            res = max_api_call(f"/api/v1/events{params}", token=token)
            
            if "error" in res:
                time.sleep(10)
                continue
                
            events = res.get("events", [])
            for ev in events:
                last_event_id = ev.get("id", last_event_id)
                if ev.get("type") == "message_created":
                    msg = ev.get("message", {})
                    chat_id = msg.get("chat_id")
                    text = msg.get("text", "").strip()
                    
                    if text.lower() in ["/start", "/help", "помощь"]:
                        send_max_message(chat_id, "🚀 HomeServer AI Hub активен в мессенджере MAX!\nЗадавайте любые вопросы или просите план дня.", token)
                    elif text.lower() in ["/plan", "план"]:
                        plan = load_daily_plan()
                        send_max_message(chat_id, f"📅 План на сегодня: {plan.get('topic', 'Учеба')}", token)
                    elif text.lower() in ["/status", "статус"]:
                        send_max_message(chat_id, f"📊 Статус HomeServer:\n{get_status_text()}", token)
                    else:
                        resp = ask_chat_agent(text, user_name="User")
                        send_max_message(chat_id, f"🤖 {sanitize_outgoing_text(resp.get('response', ''))}", token)
                        
            time.sleep(2)
        except Exception as e:
            print(f"[MAX Bot] Ошибка цикла: {e}")
            time.sleep(5)

def start_max_bot_thread():
    t = threading.Thread(target=run_max_bot_polling, daemon=True, name="MAXBotThread")
    t.start()
    return t

if __name__ == "__main__":
    run_max_bot_polling()
