





# -*- coding: utf-8 -*-
"""
HomeServer MAX Messenger Bot Integration
Connects to official MAX Bot API (platform-api2.max.ru / max-botapi-python).
"""
import os
import sys
import json
import time
import re
import ssl
import urllib.request
import urllib.parse
import urllib.error
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Any

# ===== НАСТРОЙКА КОДИРОВКИ =====
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ===== ПУТИ =====
BASE_DIR = Path("C:/HomeServer")
CONFIG_PATH = BASE_DIR / "config" / ".env"
INBOX_DIR = BASE_DIR / "inbox"
SCRIPTS_DIR = BASE_DIR / "scripts"
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_DIR.mkdir(exist_ok=True)

sys.path.append(str(SCRIPTS_DIR))

# ===== ИМПОРТЫ МОДУЛЕЙ HOMESERVER =====
try:
    from core.chat_agent import ask_chat_agent
    from core.audio_transcriber import transcribe_audio_file
    from core.study_planner import load_daily_plan
    from core.system_status import get_status_text
except ImportError as e:
    print(f"[MAX Bot] WARNING: core modules not loaded: {e}")
    def ask_chat_agent(text, user_name=None):
        return {"response": f"Processed: {text[:100]}..."}
    def load_daily_plan():
        return {"topic": "Preparation for SHAD", "tasks": []}
    def get_status_text():
        return "CPU: 10%, RAM: 50%"

# ===== SSL CONFIG =====
SSL_CTX = ssl._create_unverified_context()
MAX_API_BASE = "https://botapi.max.ru"

# ===== CONTEXT MANAGER =====
class ContextManager:
    """Manages dialog context for each user"""
    
    def __init__(self, memory_dir: Path):
        self.memory_dir = memory_dir
        self.contexts: Dict[str, Dict] = {}
        self.max_history = 20
    
    def get_context(self, user_id: str) -> Dict:
        if user_id not in self.contexts:
            self.contexts[user_id] = {
                "history": [],
                "last_action": None,
                "pending_file": None,
                "current_topic": None,
                "user_name": None,
                "last_interaction": datetime.now().isoformat()
            }
            self._load_context(user_id)
        return self.contexts[user_id]
    
    def add_message(self, user_id: str, message: str, is_user: bool = True):
        ctx = self.get_context(user_id)
        ctx["history"].append({
            "role": "user" if is_user else "assistant",
            "content": message,
            "timestamp": datetime.now().isoformat()
        })
        ctx["last_interaction"] = datetime.now().isoformat()
        if len(ctx["history"]) > self.max_history:
            ctx["history"] = ctx["history"][-self.max_history:]
        self._save_context(user_id)
    
    def set_pending_file(self, user_id: str, file_info: Dict):
        ctx = self.get_context(user_id)
        ctx["pending_file"] = file_info
    
    def get_pending_file(self, user_id: str) -> Optional[Dict]:
        ctx = self.get_context(user_id)
        file_info = ctx.get("pending_file")
        ctx["pending_file"] = None
        return file_info
    
    def set_topic(self, user_id: str, topic: str):
        ctx = self.get_context(user_id)
        ctx["current_topic"] = topic
    
    def get_context_summary(self, user_id: str) -> str:
        ctx = self.get_context(user_id)
        if not ctx["history"]:
            return ""
        recent = ctx["history"][-5:]
        summary = "Previous dialog:\n"
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            summary += f"{role}: {msg['content'][:100]}...\n"
        if ctx["current_topic"]:
            summary += f"\nCurrent topic: {ctx['current_topic']}"
        return summary
    
    def _save_context(self, user_id: str):
        try:
            file_path = self.memory_dir / f"context_{user_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.contexts[user_id], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[MAX Bot] Failed to save context: {e}")
    
    def _load_context(self, user_id: str):
        try:
            file_path = self.memory_dir / f"context_{user_id}.json"
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.contexts[user_id].update(saved)
        except Exception as e:
            print(f"[MAX Bot] Failed to load context: {e}")

# ===== MAX API FUNCTIONS =====
def get_max_config() -> str:
    token = os.getenv("MAX_BOT_TOKEN", "")
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MAX_BOT_TOKEN="):
                    token = line.strip().split("=", 1)[1].strip()
                    break
    return token

def get_max_opener():
    proxy = os.getenv("MAX_PROXY_URL", "").strip()
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MAX_PROXY_URL="):
                    proxy = line.strip().split("=", 1)[1].strip()
                    break
    handlers = [urllib.request.HTTPSHandler(context=SSL_CTX)]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)

def max_api_call(endpoint: str, data: dict = None, token: str = "", method: str = None) -> dict:
    url = f"{MAX_API_BASE}{endpoint}"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "HomeServer-MAX-Bot/2.0"
    }
    req_data = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    opener = get_max_opener()
    try:
        with opener.open(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')[:200]
        return {"error": f"HTTP {e.code}: {error_body}"}
    except urllib.error.URLError as e:
        return {"error": f"URL Error: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}

def send_max_message(user_id: str, text: str, token: str) -> dict:
    payload = {"text": text[:4000]}
    res = max_api_call(f"/messages?user_id={user_id}", payload, token)
    if "error" in res:
        print(f"[MAX Bot] Send error: {res['error']}")
    return res

def send_typing_status(user_id: str, token: str):
    try:
        max_api_call(f"/typing?user_id={user_id}", token=token)
    except Exception:
        pass

# ===== MESSAGE PROCESSING =====
def sanitize_outgoing_text(text: str) -> str:
    if not text:
        return ""
    t = str(text)
    t = re.sub(r'[a-zA-Z]:\\\\[hH]ome[sS]erver\\\\[a-zA-Z0-9_\\\\-]+', '[STORAGE_PATH]', t)
    t = re.sub(r'\b192\.168\.\d{1,3}\.\d{1,3}\b', '[LOCAL_IP]', t)
    t = re.sub(r'\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[VPN_IP]', t)
    t = re.sub(r'\b(?:sk-[a-zA-Z0-9_-]{20,}|AQ\.[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{20,})\b', '[PROTECTED_KEY]', t)
    return t

def process_message(text: str, user_id: str, user_name: str, 
                   context_mgr: ContextManager, token: str) -> str:
    context_mgr.add_message(user_id, text)
    pending_file = context_mgr.get_pending_file(user_id)
    text_lower = text.lower().strip()
    
    # ----- COMMANDS -----
    if text_lower in ["/start", "/help", "help", "помощь"]:
        response = (
            "HomeServer AI Hub active in MAX messenger!\n\n"
            "Commands:\n"
            "/status - Server status\n"
            "/plan - Today's plan\n"
            "/clear - Clear dialog history\n"
            "/context - Show context\n\n"
            "Just ask questions - I remember the context!"
        )
        context_mgr.set_topic(user_id, "main_menu")
        return response
    
    elif text_lower in ["/status", "status", "статус"]:
        status = get_status_text()
        return f"HomeServer status:\n{status}\n\nYour MAX ID: {user_id}"
    
    elif text_lower in ["/plan", "plan", "план"]:
        plan = load_daily_plan()
        return f"Today's plan:\n\nTopic: {plan.get('topic', 'Study')}\nTasks: {', '.join(plan.get('tasks', ['No tasks']))}"
    
    elif text_lower in ["/clear", "clear", "очистить"]:
        context_mgr.contexts[user_id] = {
            "history": [],
            "last_action": None,
            "pending_file": None,
            "current_topic": None,
            "user_name": user_name,
            "last_interaction": datetime.now().isoformat()
        }
        return "Dialog history cleared."
    
    elif text_lower in ["/context", "context", "контекст"]:
        summary = context_mgr.get_context_summary(user_id)
        if not summary:
            return "Dialog history is empty."
        return f"Dialog context:\n{summary}"
    
    # ----- FILE HANDLING -----
    if pending_file:
        file_path = Path(pending_file["path"])
        file_name = pending_file["name"]
        file_type = pending_file["type"]
        response = f"Processing file: {file_name}\n"
        if file_type == 'image':
            response += "Image saved to INBOX. I can recognize text from it if needed."
        elif file_type == 'audio':
            try:
                from core.audio_transcriber import transcribe_audio_file
                transcript = transcribe_audio_file(str(file_path))
                if transcript:
                    response += f"Audio transcription:\n{transcript[:500]}"
                else:
                    response += "Could not transcribe audio."
            except Exception as e:
                response += f"Transcription error: {e}"
        elif file_type == 'text':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(2000)
                response += f"File content:\n{content}"
            except Exception:
                response += "Could not read file."
        else:
            response += f"File saved to INBOX. Type: {file_type}"
        context_mgr.add_message(user_id, response, is_user=False)
        return response
    
    # ----- AI QUERY -----
    context_summary = context_mgr.get_context_summary(user_id)
    full_query = f"{context_summary}\n\nNew question: {text}" if context_summary else text
    
    try:
        resp = ask_chat_agent(full_query, user_name=user_name)
        response = resp.get('response', 'Could not get response.')
    except Exception as e:
        response = f"AI error: {str(e)}"
    
    response = sanitize_outgoing_text(response)
    context_mgr.add_message(user_id, response, is_user=False)
    return response

# ===== POLLING LOOP =====
def run_max_bot_polling():
    token = get_max_config()
    if not token:
        print("[MAX Bot] MAX_BOT_TOKEN not set. Bot in waiting mode.")
        return
    
    me = max_api_call("/me", token=token)
    if "error" in me:
        print(f"[MAX Bot] Connection error: {me['error']}")
        return
    
    bot_name = me.get("username", "unknown")
    print(f"[MAX Bot] Starting MAX Bot Polling... Bot: @{bot_name}")
    print(f"[MAX Bot] Context manager active")
    
    context_mgr = ContextManager(MEMORY_DIR)
    last_marker = None
    consecutive_errors = 0
    max_errors = 10
    
    while True:
        try:
            token = get_max_config()
            if not token:
                print("[MAX Bot] Token lost, waiting...")
                time.sleep(10)
                continue
            
            params = f"?timeout=25&limit=10"
            if last_marker:
                params += f"&marker={last_marker}"
            
            res = max_api_call(f"/updates{params}", token=token)
            
            if "error" in res:
                print(f"[MAX Bot] Polling error: {res['error']}")
                consecutive_errors += 1
                if consecutive_errors > max_errors:
                    print("[MAX Bot] Too many errors, restarting in 30s")
                    time.sleep(30)
                    consecutive_errors = 0
                else:
                    time.sleep(5)
                continue
            
            consecutive_errors = 0
            last_marker = res.get("marker", last_marker)
            
            events = res.get("updates", [])
            for ev in events:
                update_type = ev.get("update_type")
                
                if update_type == "message_created":
                    msg = ev.get("message", {})
                    sender = msg.get("sender", {})
                    sender_user_id = str(sender.get("user_id"))
                    text = msg.get("body", {}).get("text", "").strip()
                    sender_name = sender.get("name") or sender.get("first_name") or "User"
                    
                    if not sender_user_id:
                        continue
                    
                    print(f"[MAX Bot] Message from {sender_name} (id:{sender_user_id}): {text[:60]}")
                    send_typing_status(sender_user_id, token)
                    response = process_message(text, sender_user_id, sender_name, context_mgr, token)
                    if response:
                        send_max_message(sender_user_id, response, token)
                
                elif update_type == "file_uploaded":
                    file_data = ev.get("file", {})
                    sender = ev.get("sender", {})
                    sender_user_id = str(sender.get("user_id"))
                    if not sender_user_id:
                        continue
                    print(f"[MAX Bot] File from {sender_user_id}: {file_data.get('file_name', 'unknown')}")
                    context_mgr.set_pending_file(sender_user_id, file_data)
                    send_max_message(sender_user_id, "File received. What should I do with it?", token)
        
        except KeyboardInterrupt:
            print("[MAX Bot] Stopped by user request")
            break
        except Exception as e:
            print(f"[MAX Bot] Critical error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(10)

def start_max_bot_thread():
    t = threading.Thread(target=run_max_bot_polling, daemon=True, name="MAXBotThread")
    t.start()
    return t

if __name__ == "__main__":
    run_max_bot_polling()