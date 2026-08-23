import ssl
SSL_CTX = ssl._create_unverified_context()
# -*- coding: utf-8 -*-
"""
HomeServer Telegram Bot Integration (Long Polling)
Supports text AI dialog, voice note transcription, document ingestion to INBOX, and Reply Keyboards.
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
from core.quiz_engine import generate_quiz_question
from tasks.file_ai_organizer import scan_and_process_inbox

def get_tg_config():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    user_id = os.getenv("TELEGRAM_USER_ID", "")
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.strip().split("=", 1)[1]
                elif line.startswith("TELEGRAM_USER_ID="):
                    user_id = line.strip().split("=", 1)[1]
    return token.strip(), user_id.strip()

def tg_call(method: str, params: dict, token: str) -> dict:
    data = json.dumps(params).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=35) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def build_tg_keyboard():
    return {
        "keyboard": [
            [{"text": "📅 План на день"}, {"text": "📊 Статус ПК"}],
            [{"text": "📥 Проверить Inbox"}, {"text": "📝 Тест ШАД / DS"}]
        ],
        "resize_keyboard": True
    }

def send_tg_message(chat_id: int, text: str, token: str, keyboard: dict = None):
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for idx, chunk in enumerate(chunks):
        params = {"chat_id": chat_id, "text": chunk}
        if keyboard and idx == len(chunks) - 1:
            params["reply_markup"] = keyboard
        tg_call("sendMessage", params, token)

def handle_tg_message(msg: dict, token: str, allowed_user_id: str):
    chat_id = msg.get("chat", {}).get("id")
    from_user = msg.get("from", {})
    sender_id = from_user.get("id")
    text = msg.get("text", "").strip()

    if allowed_user_id and str(sender_id) != str(allowed_user_id):
        send_tg_message(chat_id, "🔒 Доступ ограничен. Ваш Telegram ID не авторизован в конфигурации HomeServer.", token)
        return

    keyboard = build_tg_keyboard()

    # 1. Voice / Audio Message
    voice = msg.get("voice") or msg.get("audio")
    voice_text = ""
    if voice:
        file_id = voice.get("file_id")
        file_info = tg_call("getFile", {"file_id": file_id}, token)
        if file_info.get("ok"):
            file_path = file_info.get("result", {}).get("file_path")
            download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            send_tg_message(chat_id, "🎙️ Голосовое сообщение получено, выполняю транскрибацию...", token)
            temp_file = BASE_DIR / "inbox" / f"tg_voice_{int(time.time())}.oga"
            try:
                urllib.request.urlretrieve(download_url, str(temp_file))
                voice_text = transcribe_audio_file(temp_file)
                if voice_text:
                    send_tg_message(chat_id, f"📝 Распознано: «{voice_text}»", token)
                temp_file.unlink(missing_ok=True)
            except Exception as e:
                print(f"[TG Voice Error]: {e}")

    # 2. Document upload to INBOX
    doc = msg.get("document")
    if doc:
        file_id = doc.get("file_id")
        file_name = doc.get("file_name", f"tg_file_{int(time.time())}.bin")
        file_info = tg_call("getFile", {"file_id": file_id}, token)
        if file_info.get("ok"):
            file_path = file_info.get("result", {}).get("file_path")
            download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            INBOX_DIR.mkdir(parents=True, exist_ok=True)
            dest = INBOX_DIR / file_name
            try:
                urllib.request.urlretrieve(download_url, str(dest))
                send_tg_message(chat_id, f"📥 Файл «{file_name}» сохранен в INBOX. Анализирую...", token, keyboard)
                scan_and_process_inbox(auto_apply=False)
                send_tg_message(chat_id, f"✅ Предложение по сортировке для «{file_name}» готово!", token, keyboard)
            except Exception as e:
                send_tg_message(chat_id, f"⚠️ Ошибка загрузки: {e}", token, keyboard)

    query = voice_text if voice_text else text
    if not query:
        return

    q_lower = query.lower()

    if q_lower in ["/start", "/help", "начать", "помощь", "привет"]:
        welcome = (
            "🚀 HomeServer AI Hub активен в Telegram!\n\n"
            "• Задавайте любые вопросы AI (Gemini Flash + DeepSeek)\n"
            "• Надиктовывайте голосовые заметки\n"
            "• Присылайте PDF/файлы для автосортировки в архив\n"
            "• Используйте кнопки быстрого меню 👇"
        )
        send_tg_message(chat_id, welcome, token, keyboard)
        return

    if q_lower in ["📅 план на день", "/plan", "план"]:
        plan = load_daily_plan()
        res_text = f"📅 План на сегодня:\n🎯 {plan.get('topic', 'Учеба')}\n\n"
        for idx, t in enumerate(plan.get("tasks", []), 1):
            res_text += f"{idx}. {t}\n"
        send_tg_message(chat_id, res_text, token, keyboard)
        return

    if q_lower in ["📊 статус пк", "/status", "статус"]:
        send_tg_message(chat_id, f"📊 Статус HomeServer:\n\n{get_status_text()}", token, keyboard)
        return

    if q_lower in ["📥 проверить inbox", "/inbox", "инбокс"]:
        inbox_files = list(INBOX_DIR.glob("*")) if INBOX_DIR.exists() else []
        clean = [f.name for f in inbox_files if not f.name.startswith(".")]
        res_text = f"📥 В папке INBOX {len(clean)} файлов:\n" + "\n".join([f"• {n}" for n in clean]) if clean else "📥 Папка INBOX пуста!"
        send_tg_message(chat_id, res_text, token, keyboard)
        return

    if q_lower in ["📝 тест шад / ds", "/quiz", "викторина"]:
        q = generate_quiz_question()
        res_text = f"📝 Викторина ШАД:\n\n❓ {q.get('question')}\n\n" + "\n".join([f"• {o}" for o in q.get("options", [])])
        send_tg_message(chat_id, res_text, token, keyboard)
        return

    # AI query
    try:
        ai_resp = ask_chat_agent(query, user_name="User")
        send_tg_message(chat_id, f"🤖 {ai_resp.get('response', '')}", token, keyboard)
    except Exception as e:
        send_tg_message(chat_id, f"⚠️ Ошибка: {e}", token, keyboard)

def run_tg_bot_polling():
    token, allowed_user_id = get_tg_config()
    if not token:
        print("[Telegram Bot] ⚪ TELEGRAM_BOT_TOKEN не задан в .env. Бот Telegram в режиме ожидания токена.")
        return

    print("[Telegram Bot] 🟢 Запуск Telegram Bot Long Polling...")
    offset = 0
    while True:
        try:
            token, allowed_user_id = get_tg_config()
            if not token:
                time.sleep(10)
                continue

            res = tg_call("getUpdates", {"offset": offset, "timeout": 25}, token)
            if not res.get("ok"):
                time.sleep(5)
                continue

            for upd in res.get("result", []):
                offset = upd.get("update_id", offset) + 1
                if "message" in upd:
                    handle_tg_message(upd["message"], token, allowed_user_id)

        except Exception as e:
            print(f"[Telegram Bot] Ошибка цикла: {e}")
            time.sleep(5)

def start_telegram_bot_thread():
    t = threading.Thread(target=run_tg_bot_polling, daemon=True, name="TelegramBotThread")
    t.start()
    return t

if __name__ == "__main__":
    run_tg_bot_polling()
