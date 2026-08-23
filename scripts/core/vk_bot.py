# -*- coding: utf-8 -*-
"""
HomeServer VK Bot Integration (Long Polling)
Supports text AI dialog, voice notes transcription, document uploads to INBOX, and Quick Actions keyboard.
"""
import os
import sys
import re
import json
import time
import ssl
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
from core.study_planner import load_daily_plan, get_today_plan
from core.system_status import get_status_text
from core.quiz_engine import generate_quiz_question, check_quiz_answer
from tasks.file_ai_organizer import scan_and_process_inbox

VK_API_VERSION = "5.199"
SSL_CTX = ssl._create_unverified_context()

def get_vk_opener():
    proxy = os.getenv("VK_PROXY_URL", "").strip()
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VK_PROXY_URL="):
                        proxy = line.strip().split("=", 1)[1].strip().strip("'\"")
        except Exception:
            pass
    handlers = [urllib.request.HTTPSHandler(context=SSL_CTX)]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)

def sanitize_outgoing_text(text: str) -> str:
    """Удаляет из ответов локальные пути, внутренние IP и токены перед отправкой в VK."""
    t = str(text)
    t = re.sub(r'[a-zA-Z]:\\[hH]ome[sS]erver\\[a-zA-Z0-9_\\-]+', '[STORAGE_PATH]', t)
    t = re.sub(r'\b192\.168\.\d{1,3}\.\d{1,3}\b', '[LOCAL_IP]', t)
    t = re.sub(r'\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[VPN_IP]', t)
    t = re.sub(r'\b(?:sk-[a-zA-Z0-9_-]{20,}|AQ\.[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{20,})\b', '[PROTECTED_KEY]', t)
    return t

def get_vk_config():
    token = os.getenv("VK_BOT_TOKEN", "")
    user_id = os.getenv("VK_USER_ID", "")
    group_id = os.getenv("VK_GROUP_ID", "")
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("VK_BOT_TOKEN="):
                        token = line.split("=", 1)[1]
                    elif line.startswith("VK_USER_ID="):
                        user_id = line.split("=", 1)[1]
                    elif line.startswith("VK_GROUP_ID="):
                        group_id = line.split("=", 1)[1]
        except Exception as e:
            print(f"[VK Config Error]: {e}")
    return token.strip().strip("'\""), user_id.strip().strip("'\""), group_id.strip().strip("'\"")

def vk_api_call(method: str, params: dict, token: str) -> dict:
    params["access_token"] = token
    params["v"] = VK_API_VERSION
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(f"https://api.vk.com/method/{method}", data=data)
    opener = get_vk_opener()
    try:
        with opener.open(req, timeout=35) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"[VK API Error] {method}: {e}")
        return {"error": str(e)}

def build_vk_keyboard():
    keyboard = {
        "one_time": False,
        "buttons": [
            [
                {"action": {"type": "text", "label": "🎓 Наставник", "payload": "{\"cmd\": \"mentor\"}"}, "color": "primary"},
                {"action": {"type": "text", "label": "👑 Мультиагент", "payload": "{\"cmd\": \"multiagent\"}"}, "color": "positive"}
            ],
            [
                {"action": {"type": "text", "label": "🕵️ Инкогнито", "payload": "{\"cmd\": \"incognito\"}"}, "color": "secondary"},
                {"action": {"type": "text", "label": "🧠 Память", "payload": "{\"cmd\": \"memory\"}"}, "color": "secondary"}
            ],
            [
                {"action": {"type": "text", "label": "📅 План на день", "payload": "{\"cmd\": \"plan\"}"}, "color": "secondary"},
                {"action": {"type": "text", "label": "📊 Статус ПК", "payload": "{\"cmd\": \"status\"}"}, "color": "secondary"}
            ]
        ]
    }
    return json.dumps(keyboard, ensure_ascii=False)

def send_vk_message(peer_id: int, message: str, token: str, keyboard: str = None, attachment: str = None):
    chunks = [message[i:i+4000] for i in range(0, len(message), 4000)] if message else [""]
    for idx, chunk in enumerate(chunks):
        params = {
            "peer_id": peer_id,
            "message": chunk,
            "random_id": int(time.time() * 1000) % 2147483647
        }
        if attachment and idx == len(chunks) - 1:
            params["attachment"] = attachment
        if keyboard and idx == len(chunks) - 1:
            params["keyboard"] = keyboard
        res = vk_api_call("messages.send", params, token)
        
        # Fallback for Error 912 (Chat bot features disabled in VK group settings)
        if "error" in res:
            err = res.get("error", {})
            err_code = err.get("error_code") if isinstance(err, dict) else None
            if err_code == 912 or "chat bot feature" in str(err).lower():
                # Retry without keyboard attachment
                params.pop("keyboard", None)
                params["random_id"] = int(time.time() * 1000) % 2147483647
                res = vk_api_call("messages.send", params, token)
            if "error" in res:
                print(f"[VK Send Error] peer_id={peer_id}: {res.get('error')}")

def send_vk_document(peer_id: int, file_path: str, token: str, title: str = None, message: str = "") -> bool:
    try:
        import requests
        p = Path(file_path)
        if not p.exists():
            print(f"[VK Doc Error] Файл не найден: {file_path}")
            return False
        
        srv_res = vk_api_call("docs.getMessagesUploadServer", {"peer_id": peer_id, "type": "doc"}, token)
        upload_url = srv_res.get("response", {}).get("upload_url")
        if not upload_url:
            print(f"[VK Doc Error] Не получен upload_url: {srv_res}")
            return False

        with open(p, "rb") as f:
            r = requests.post(upload_url, files={"file": (title or p.name, f)}, timeout=60)
            upload_data = r.json()

        file_payload = upload_data.get("file")
        if not file_payload:
            print(f"[VK Doc Error] Ошибка загрузки файла: {upload_data}")
            return False

        save_res = vk_api_call("docs.save", {"file": file_payload, "title": title or p.name}, token)
        doc_obj = None
        if "response" in save_res:
            resp = save_res["response"]
            if isinstance(resp, dict):
                doc_obj = resp.get("doc")
            elif isinstance(resp, list) and len(resp) > 0:
                doc_obj = resp[0]

        if not doc_obj:
            print(f"[VK Doc Error] Ошибка сохранения документа: {save_res}")
            return False

        doc_id = doc_obj["id"]
        owner_id = doc_obj["owner_id"]
        attachment = f"doc{owner_id}_{doc_id}"

        msg_body = message if message else f"📎 Файл: {title or p.name}"
        send_vk_message(peer_id, sanitize_outgoing_text(msg_body), token, attachment=attachment)
        return True
    except Exception as e:
        print(f"[VK Doc Upload Exception]: {e}")
        return False

def handle_vk_event(item: dict, token: str, allowed_user_id: str):
    if not item:
        return
        
    if "message" in item:
        msg = item["message"]
    else:
        msg = item

    peer_id = msg.get("peer_id")
    from_id = msg.get("from_id", peer_id)
    text = msg.get("text", "").strip()
    attachments = msg.get("attachments", [])

    if not peer_id:
        return

    # Security whitelist check if configured
    if allowed_user_id:
        allowed_list = [u.strip().strip("'\"") for u in str(allowed_user_id).split(",") if u.strip().strip("'\"")]
        if allowed_list and str(from_id) not in allowed_list and str(peer_id) not in allowed_list:
            print(f"[VK] Отклонено сообщение от неавторизованного пользователя: from_id={from_id}, peer_id={peer_id}")
            send_vk_message(peer_id, "🔒 Доступ к HomeServer ограничен. Ваш VK ID не авторизован в настройках сервера.", token)
            return

    keyboard = build_vk_keyboard()

    # 1. Voice Message handling
    voice_transcribed = ""
    for att in attachments:
        att_type = att.get("type")
        if att_type in ["audio_message", "doc"] and att.get(att_type, {}).get("type") in [5, "audio_message"]:
            audio_info = att.get(att_type, {})
            link_ogg = audio_info.get("link_ogg") or audio_info.get("link_mp3")
            if link_ogg:
                try:
                    send_vk_message(peer_id, "🎙️ Получено голосовое сообщение, расшифровываю...", token)
                    temp_audio = BASE_DIR / "inbox" / f"vk_voice_{int(time.time())}.ogg"
                    urllib.request.urlretrieve(link_ogg, str(temp_audio))
                    transcript = transcribe_audio_file(temp_audio)
                    if transcript:
                        voice_transcribed = transcript
                        send_vk_message(peer_id, f"📝 Распознано: «{transcript}»", token)
                    temp_audio.unlink(missing_ok=True)
                except Exception as e:
                    print(f"[VK Voice Error]: {e}")

    # 2. File / Document attachments handling (saving directly to INBOX)
    for att in attachments:
        att_type = att.get("type")
        if att_type == "doc" and not voice_transcribed:
            doc = att.get("doc", {})
            title = doc.get("title", f"vk_file_{int(time.time())}.bin")
            url = doc.get("url")
            if url:
                try:
                    INBOX_DIR.mkdir(parents=True, exist_ok=True)
                    dest_file = INBOX_DIR / title
                    urllib.request.urlretrieve(url, str(dest_file))
                    send_vk_message(peer_id, f"📥 Документ «{title}» успешно сохранен в INBOX. Запускаю AI-анализ...", token, keyboard)
                    scan_and_process_inbox(auto_apply=False)
                    send_vk_message(peer_id, f"✅ Предложение по сортировке для «{title}» сформировано!", token, keyboard)
                except Exception as e:
                    send_vk_message(peer_id, f"⚠️ Ошибка сохранения файла: {e}", token, keyboard)

    # Determine active query
    query = voice_transcribed if voice_transcribed else text

    if not query and attachments:
        return

    q_lower = query.lower().strip()

    # Commands router
    if q_lower in ["/start", "/help", "начать", "помощь", "привет", "меню", "start", "help"]:
        welcome = (
            "🚀 HomeServer Multi-Channel AI Hub активен!\n\n"
            "Вы можете:\n"
            "• Задавать любые вопросы AI (Gemini Flash + DeepSeek)\n"
            "• Отправлять голосовые сообщения (сервер расшифрует и ответит)\n"
            "• Присылать документы и файлы (автоматически попадают в INBOX)\n"
            "• Использовать кнопки быстрого доступа ниже 👇"
        )
        send_vk_message(peer_id, welcome, token, keyboard)
        return

    if q_lower in ["📅 план на день", "/plan", "план", "план на сегодня", "план на день"]:
        plan = load_daily_plan()
        if not plan:
            plan = get_today_plan()
        msg_text = f"📅 План на сегодня:\n🎯 Тема: {plan.get('topic', 'Учеба и задачи')}\n\nЗадачи:\n"
        for idx, task in enumerate(plan.get("tasks", []), 1):
            msg_text += f"{idx}. {task}\n"
        send_vk_message(peer_id, msg_text, token, keyboard)
        return

    if q_lower in ["📊 статус пк", "/status", "статус", "статус пк"]:
        status = get_status_text()
        send_vk_message(peer_id, f"📊 Статус HomeServer:\n\n{status}", token, keyboard)
        return

    if q_lower in ["📥 проверить inbox", "/inbox", "инбокс", "inbox"]:
        inbox_files = list(INBOX_DIR.glob("*")) if INBOX_DIR.exists() else []
        clean_files = [f.name for f in inbox_files if not f.name.startswith(".")]
        if clean_files:
            msg_text = f"📥 В папке INBOX ({len(clean_files)} файлов):\n" + "\n".join([f"• {name}" for name in clean_files])
        else:
            msg_text = "📥 Папка INBOX пуста. Все файлы обработаны и разложены по архивам!"
        send_vk_message(peer_id, msg_text, token, keyboard)
        return

    if q_lower in ["📝 тест шад / ds", "/quiz", "викторина", "тест"]:
        q_data = generate_quiz_question()
        msg_text = f"📝 Викторина ШАД / Data Science:\n\n❓ Вопрос: {q_data.get('question')}\n\nВарианты:\n"
        for opt in q_data.get("options", []):
            msg_text += f"• {opt}\n"
        msg_text += "\n💡 Отправьте ваш ответ сообщением!"
        send_vk_message(peer_id, msg_text, token, keyboard)
        return

    DRIVERS_ZIP_DIR = Path("C:/Users/user/Desktop/Драйверы_для_сканеров_ZIP")
    DESKTOP_DIR = Path("C:/Users/user/Desktop")

    if any(k in q_lower for k in ["драйвер honeywell", "honeywell", "орбит", "orbit", "hsm"]):
        send_vk_message(peer_id, "⏳ Отправляю официальный драйвер Honeywell HSM USB Serial v3.5.20...", token)
        hsm_file = DRIVERS_ZIP_DIR / "01_Honeywell_HSM_USB_Serial_Driver_v3.5.20.zip"
        if not hsm_file.exists():
            hsm_file = DESKTOP_DIR / "HSM_USB_Serial_Driver_v3.5.20_signed.zip"
        if hsm_file.exists():
            send_vk_document(peer_id, str(hsm_file), token, title="HSM_USB_Serial_Driver_v3.5.20_signed.zip", message="✅ Официальный драйвер Honeywell Orbit 7120/7190g (Win10/11 x64 & x86):")
        hw_bc = DRIVERS_ZIP_DIR / "05_Штрихкоды_настройки_Honeywell_Orbit.zip"
        if hw_bc.exists():
            send_vk_document(peer_id, str(hw_bc), token, title="Barcodes_Honeywell_Orbit_7120_7190g.zip", message="📄 Сервисные штрихкоды MetroSelect для настройки Orbit:")
        return

    if any(k in q_lower for k in ["драйвер mertech", "драйвер sunmi", "sunmi", "mertech", "superlead", "ns021"]):
        send_vk_message(peer_id, "⏳ Отправляю драйверы для сканера Sunmi / Mertech NS021...", token)
        sl_file = DRIVERS_ZIP_DIR / "02_Mertech_Sunmi_SuperLead_UsbComDriver_V2.15.0.zip"
        if sl_file.exists():
            send_vk_document(peer_id, str(sl_file), token, title="SuperLead_UsbComDriver_V2.15.0.zip", message="✅ Основной драйвер Mertech / Sunmi / SuperLead V2.15.0:")
        sunmi_bc = DRIVERS_ZIP_DIR / "04_Штрихкоды_настройки_Sunmi_Mertech_NS021.zip"
        if sunmi_bc.exists():
            send_vk_document(peer_id, str(sunmi_bc), token, title="Barcodes_Sunmi_Mertech_NS021.zip", message="📄 Управляющие штрихкоды Sunmi/Mertech (Честный Знак, USB-COM, GS):")
        return

    # AI query processing
    try:
        # Resolve username from bound VK ID
        bound_user = "ardont"
        try:
            from core.auth_manager import get_user_by_vk_id
            u_info = get_user_by_vk_id(str(from_id))
            if u_info:
                bound_user = u_info.get("username", "ardont")
            elif str(from_id) == str(allowed_user_id):
                bound_user = "ardont"
        except Exception:
            bound_user = "ardont"
            
        response = ask_chat_agent(query, username=bound_user, user_name=bound_user)
        ai_text = response.get("response", "Не удалось получить ответ от AI.")
        
        file_matches = re.findall(r'\[SEND_FILE:([^\]]+)\]', ai_text)
        clean_text = re.sub(r'\[SEND_FILE:[^\]]+\]', '', ai_text).strip()
        
        if clean_text:
            send_vk_message(peer_id, f"🤖 {sanitize_outgoing_text(clean_text)}", token, keyboard)
            
        for f_path in file_matches:
            target_f = Path(f_path.strip())
            if target_f.exists():
                send_vk_document(peer_id, str(target_f), token, title=target_f.name)
            else:
                alt_f = INBOX_DIR / target_f.name
                if alt_f.exists():
                    send_vk_document(peer_id, str(alt_f), token, title=alt_f.name)
    except Exception as e:
        print(f"[VK AI Query Error]: {e}")
        send_vk_message(peer_id, f"⚠️ Ошибка обработки запроса: {e}", token, keyboard)

def run_vk_bot_polling():
    token, allowed_user_id, group_id = get_vk_config()
    if not token:
        print("[VK Bot] ⚪ VK_BOT_TOKEN не задан в .env. Бот ВКонтакте в режиме ожидания токена.")
        return

    print("[VK Bot] 🟢 Запуск VK Bot Long Polling...")
    
    while True:
        try:
            token, allowed_user_id, group_id = get_vk_config()
            if not token:
                time.sleep(10)
                continue

            # Check if group or standalone
            lp_res = vk_api_call("groups.getLongPollServer", {"group_id": group_id} if group_id else {}, token)
            if "response" not in lp_res:
                lp_res = vk_api_call("messages.getLongPollServer", {"need_pts": 0, "lp_version": 3}, token)

            if "response" not in lp_res:
                print(f"[VK Bot] ⚠️ Ошибка получения LongPoll сервера: {lp_res.get('error')}. Повтор через 15с...")
                time.sleep(15)
                continue

            server_data = lp_res["response"]
            server = server_data.get("server")
            key = server_data.get("key")
            ts = server_data.get("ts")
            
            if not server.startswith("http"):
                server = f"https://{server}"

            print(f"[VK Bot] [+] Подключено к VK LongPoll серверу (ts={ts})")

            while True:
                poll_url = f"{server}?act=a_check&key={key}&ts={ts}&wait=25"
                try:
                    req = urllib.request.Request(poll_url)
                    with urllib.request.urlopen(req, context=SSL_CTX, timeout=35) as resp:
                        poll_data = json.loads(resp.read().decode("utf-8"))
                except Exception:
                    time.sleep(3)
                    continue

                if "failed" in poll_data:
                    code = poll_data.get("failed")
                    if code == 1:
                        ts = poll_data.get("ts")
                    else:
                        break # Refresh key
                    continue

                ts = poll_data.get("ts", ts)
                updates = poll_data.get("updates", [])

                for upd in updates:
                    if isinstance(upd, dict) and upd.get("type") == "message_new":
                        handle_vk_event(upd.get("object", {}), token, allowed_user_id)
                    elif isinstance(upd, list) and upd and upd[0] == 4:
                        flags = upd[2]
                        if not (flags & 2):
                            peer_id = upd[3]
                            text = upd[5]
                            handle_vk_event({"message": {"peer_id": peer_id, "from_id": peer_id, "text": text}}, token, allowed_user_id)

        except Exception as e:
            print(f"[VK Bot] Ошибка цикла: {e}. Переподключение через 5с...")
            time.sleep(5)

def start_vk_bot_thread():
    t = threading.Thread(target=run_vk_bot_polling, daemon=True, name="VKBotThread")
    t.start()
    return t

if __name__ == "__main__":
    run_vk_bot_polling()
