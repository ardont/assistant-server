# -*- coding: utf-8 -*-
"""
HomeServer MAX Messenger Bot Integration
Connects to official MAX Bot API.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / ".env"
INBOX_DIR = BASE_DIR / "inbox"
SCRIPTS_DIR = BASE_DIR / "scripts"
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_DIR.mkdir(exist_ok=True)

sys.path.append(str(SCRIPTS_DIR))

# Импорты
try:
    from core.chat_agent import ask_chat_agent
    from core.audio_transcriber import transcribe_audio_file
    from core.study_planner import load_daily_plan
    from core.system_status import get_status_text
    from core.auth_manager import get_user_by_max_id
    from dotenv import load_dotenv
    import base64
    try:
        from google import genai
        GEMINI_AVAILABLE = True
    except ImportError:
        GEMINI_AVAILABLE = False
        print("[MAX Bot] WARNING: google-generativeai not installed")
except ImportError as e:
    print(f"[MAX Bot] WARNING: core modules not loaded: {e}")
    def ask_chat_agent(text, user_name=None):
        return {"response": f"Processed: {text[:100]}..."}
    def load_daily_plan():
        return {"topic": "Preparation for SHAD", "tasks": []}
    def get_status_text():
        return "CPU: 10%, RAM: 50%"
    def get_user_by_max_id(max_id):
        return None
    GEMINI_AVAILABLE = False

SSL_CTX = ssl._create_unverified_context()
MAX_API_BASE = "https://botapi.max.ru"

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

def download_file_from_max_direct(file_url: str, file_token: str, filename: str) -> Optional[Path]:
    try:
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        if not safe_name:
            safe_name = f"max_file_{int(time.time())}.bin"
        local_path = INBOX_DIR / safe_name
        if local_path.exists():
            stem = local_path.stem
            suffix = local_path.suffix
            local_path = INBOX_DIR / f"{stem}_{int(time.time())}{suffix}"
        req = urllib.request.Request(file_url, headers={
            "Authorization": file_token,
            "User-Agent": "HomeServer-MAX-Bot/2.0"
        })
        opener = get_max_opener()
        with opener.open(req, timeout=60) as response:
            with open(local_path, "wb") as f:
                f.write(response.read())
        print(f"[MAX Bot] File downloaded: {local_path.name} ({local_path.stat().st_size} bytes)")
        return local_path
    except Exception as e:
        print(f"[MAX Bot] Direct download error: {e}")
        return None

def detect_file_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
        return 'image'
    elif ext in ['.mp3', '.wav', '.ogg', '.m4a', '.aac']:
        return 'audio'
    elif ext in ['.pdf']:
        return 'pdf'
    elif ext in ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.csv', '.xml', '.log']:
        return 'text'
    elif ext in ['.zip', '.rar', '.7z', '.gz', '.tar']:
        return 'archive'
    else:
        return 'unknown'

def analyze_image_with_gemini(image_path: Path, question: str = "Что изображено на этом изображении? Опиши подробно.") -> str:
    """Анализирует изображение через Gemini Vision API."""
    if not GEMINI_AVAILABLE:
        return "⚠️ Gemini Vision не доступен. Установите google-generativeai: pip install google-generativeai"
    try:
        # Загружаем изображение в base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        ext = image_path.suffix.lower()
        mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else "image/png" if ext == '.png' else "image/webp" if ext == '.webp' else "image/gif" if ext == '.gif' else "image/jpeg"
        
        # Загружаем ключи
        load_dotenv(CONFIG_PATH, override=True)
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_BACKUP_KEY")
        if not api_key:
            return "⚠️ Не найден API ключ Gemini в .env"
        
        client = genai.Client(api_key=api_key)
        # Пробуем модели с поддержкой изображений
        for model_name in ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp"]:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[
                        {"role": "user", "parts": [
                            {"text": question},
                            {"inline_data": {"mime_type": mime_type, "data": image_data}}
                        ]}
                    ]
                )
                if response.text:
                    print(f"[MAX Bot] Gemini analysis success with model {model_name}")
                    return response.text
            except Exception as e:
                print(f"[MAX Bot] Gemini model {model_name} failed: {e}")
                continue
        return "⚠️ Не удалось проанализировать изображение ни через одну модель."
    except Exception as e:
        return f"⚠️ Ошибка анализа изображения: {e}"

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
                   context_mgr: ContextManager, token: str, 
                   attached_file_info: Optional[str] = None,
                   attached_file_path: Optional[Path] = None) -> str:
    context_mgr.add_message(user_id, text)
    pending_file = context_mgr.get_pending_file(user_id)
    text_lower = text.lower().strip()
    
    full_message = text
    if attached_file_info:
        full_message += f"\n\n[ПРИКРЕПЛЕННЫЙ ФАЙЛ]:\n{attached_file_info}"
    
    # ---- ОБРАБОТКА ИЗОБРАЖЕНИЙ (приоритет) ----
    if attached_file_path and attached_file_path.exists():
        file_type = detect_file_type(attached_file_path)
        if file_type == 'image':
            # Проверяем, есть ли в тексте просьба описать
            if text and any(word in text_lower for word in ["что", "скажи", "описать", "расскажи", "покажи"]):
                print(f"[MAX Bot] Analyzing image: {attached_file_path.name}")
                analysis = analyze_image_with_gemini(attached_file_path, text)
                if analysis and not analysis.startswith("⚠️"):
                    return f"🖼️ Анализ изображения:\n{analysis}"
                else:
                    # Если анализ не удался, отправляем сообщение об ошибке и переходим к обычному AI
                    print(f"[MAX Bot] Image analysis failed: {analysis}")
                    # Не возвращаем ошибку, а передаём вопрос в AI (как fallback)
                    full_message = f"Пользователь прислал изображение '{attached_file_path.name}' и спросил: {text}. Попробуй ответить на вопрос, используя контекст."
            else:
                return f"📎 Файл '{attached_file_path.name}' сохранён в INBOX. Спросите, что на нём написано, или дайте команду для обработки."
    
    # ---- ОБРАБОТКА КОМАНД ----
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
    
    elif text_lower.startswith("/osint "):
        target = full_message.split(maxsplit=1)[1].strip()
        from core.agent_tools import tool_osint_lookup
        try:
            res = tool_osint_lookup(target)
            return f"🔍 OSINT результат:\n{res[:3500]}"
        except Exception as e:
            return f"❌ Ошибка OSINT: {e}"
    elif text_lower == "/update":
        import threading
        def update_task():
            from core.process_manager import check_and_update_from_git
            check_and_update_from_git()
        threading.Thread(target=update_task, daemon=True).start()
        return "🔄 Инициирована проверка обновлений GitHub..."
    
    # ----- AI QUERY (с учётом контекста и возможного файла) -----
    context_summary = context_mgr.get_context_summary(user_id)
    full_query = f"{context_summary}\n\nNew question: {full_message}" if context_summary else full_message
    
    try:
        resp = ask_chat_agent(full_query, user_name=user_name)
        response = resp.get('response', 'Could not get response.')
        
        file_matches = re.findall(r'\[SEND_FILE:([^\]]+)\]', response)
        response = re.sub(r'\[SEND_FILE:[^\]]+\]', '', response).strip()
        
        if file_matches:
            cf_url = os.getenv("CLOUDFLARE_URL", "http://localhost:8000").rstrip("/")
            for f in file_matches:
                f = f.strip()
                link = f"{cf_url}/api/download/file?path={urllib.parse.quote(f)}"
                response += f"\n\n📎 Ссылка на файл '{Path(f).name}':\n{link}"
                
    except Exception as e:
        response = f"AI error: {str(e)}"
    
    response = sanitize_outgoing_text(response)
    if response:
        context_mgr.add_message(user_id, response, is_user=False)
    return response

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
                    
                    if not sender_user_id:
                        continue
                    
                    real_user = get_user_by_max_id(sender_user_id)
                    if real_user:
                        effective_username = real_user.get("username")
                        sender_name = real_user.get("display_name") or effective_username
                    else:
                        effective_username = sender.get("name") or sender.get("first_name") or "User"
                        sender_name = effective_username
                    
                    print(f"[MAX Bot] Message from {sender_name} (id:{sender_user_id}): {text[:60]}")
                    
                    # ---- ОБРАБОТКА ВЛОЖЕНИЙ ----
                    attachments = msg.get("body", {}).get("attachments", [])
                    attached_file_info = None
                    attached_file_path = None
                    
                    if attachments:
                        for att in attachments:
                            att_type = att.get("type")
                            if att_type == "file":
                                payload = att.get("payload", {})
                                file_url = payload.get("url")
                                file_token = payload.get("token")
                                file_id = payload.get("fileId")
                                file_name = att.get("filename", "unknown")
                                if file_url and file_token:
                                    local_path = download_file_from_max_direct(file_url, file_token, file_name)
                                    if local_path:
                                        file_type = detect_file_type(local_path)
                                        attached_file_path = local_path
                                        attached_file_info = f"File: {file_name} (saved to {local_path})"
                                        context_mgr.set_pending_file(sender_user_id, {
                                            "path": str(local_path),
                                            "name": file_name,
                                            "type": file_type,
                                            "uploaded_at": datetime.now().isoformat()
                                        })
                                        # Отправляем уведомление о загрузке
                                        send_max_message(
                                            sender_user_id,
                                            f"📎 Файл '{file_name}' получен и сохранён в INBOX. Что с ним сделать?",
                                            token
                                        )
                                        break  # берём первый файл
                    
                    send_typing_status(sender_user_id, token)
                    response = process_message(
                        text, sender_user_id, sender_name,
                        context_mgr, token,
                        attached_file_info=attached_file_info,
                        attached_file_path=attached_file_path
                    )
                    if response:
                        send_max_message(sender_user_id, response, token)
                
                elif update_type == "file_uploaded":
                    # Обработка отдельного события файла (оставляем как fallback)
                    file_data = ev.get("file", {})
                    sender = ev.get("sender", {})
                    sender_user_id = str(sender.get("user_id"))
                    if not sender_user_id:
                        continue
                    file_id = file_data.get("id")
                    file_name = file_data.get("name") or "unknown"
                    print(f"[MAX Bot] File upload event from {sender_user_id}: {file_name}")
                    if file_id:
                        send_max_message(
                            sender_user_id,
                            f"📎 Файл '{file_name}' получен (обработка через основное сообщение)",
                            token
                        )
        
        except KeyboardInterrupt:
            print("[MAX Bot] Stopped by user request")
            break
        except Exception as e:
            import traceback
            from core.notifier import notify_error
            from core.process_manager import check_and_update_from_git
            
            err_msg = traceback.format_exc()
            print(f"[MAX Bot] Critical error: {e}\n{err_msg}")
            
            alert_msg = f"🚨 FATAL ERROR IN MAX BOT:\n{e}\n\nTraceback:\n{err_msg[-1500:]}"
            notify_error("MAX Bot Crash", alert_msg)
            
            try:
                # Попытаться отправить админу в MAX
                admin_id = os.getenv("MAX_USER_ID", "")
                if admin_id:
                    send_max_message(admin_id, alert_msg, token)
            except:
                pass
                
            print("[MAX Bot] Вход в режим автовосстановления (ожидание патча с GitHub)...")
            while True:
                try:
                    check_and_update_from_git()
                except Exception as update_err:
                    print(f"[AutoUpdate] Ошибка проверки GitHub: {update_err}")
                
                time.sleep(60)

def start_max_bot_thread():
    t = threading.Thread(target=run_max_bot_polling, daemon=True, name="MAXBotThread")
    t.start()
    return t

if __name__ == "__main__":
    run_max_bot_polling()