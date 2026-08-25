# -*- coding: utf-8 -*-
"""
VK Bot 24/7 Service for HomeServer AI Hub (Jarvis)
Supports multi-user authentication, growth track queries, NotebookLM Study Guides,
voice message transcription, and proactive mentor delivery.
"""
import os
import sys
import json
import time
import re
import urllib.request
import urllib.parse
import ssl
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
CONFIG_DIR = BASE_DIR / "config"
DOCS_DIR = BASE_DIR / "documents"
INBOX_DIR = BASE_DIR / "inbox"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)
INBOX_DIR.mkdir(parents=True, exist_ok=True)

VK_API_VERSION = "5.199"

def get_vk_config() -> Tuple[str, str, str]:
    token = os.getenv("VK_COMMUNITY_TOKEN", "").strip().strip("'\"")
    user_id = os.getenv("VK_ALLOWED_USER_ID", "816140871").strip().strip("'\"")
    group_id = os.getenv("VK_GROUP_ID", "").strip().strip("'\"")
    
    # Fallback to config file if not in env
    cfg_file = CONFIG_DIR / "vk_config.json"
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                if not token:
                    token = d.get("token", "")
                if not user_id:
                    user_id = d.get("user_id", "816140871")
                if not group_id:
                    group_id = d.get("group_id", "")
        except Exception:
            pass
    return token, user_id, group_id

def send_vk_message(peer_id: int, text: str, token: str, keyboard: Optional[dict] = None) -> bool:
    if not token or not peer_id:
        return False
    url = "https://api.vk.com/method/messages.send"
    import random
    data = {
        "peer_id": peer_id,
        "message": text[:4000],
        "random_id": random.randint(1, 2147483647),
        "v": VK_API_VERSION,
        "access_token": token
    }
    if keyboard:
        data["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
        
    try:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            if "error" in res_json:
                print(f"[VK Error]: {res_json['error'].get('error_msg')}")
                return False
            return True
    except Exception as e:
        print(f"[VK Send Exception]: {e}")
        return False

def send_vk_document(peer_id: int, file_path: str, token: str, title: str = "") -> bool:
    """Загружает документ на сервера ВК и отправляет в диалог."""
    try:
        p = Path(file_path)
        if not p.exists():
            return False
        # 1. Get upload server
        url = f"https://api.vk.com/method/docs.getMessagesUploadServer?peer_id={peer_id}&v={VK_API_VERSION}&access_token={token}"
        req = urllib.request.Request(url)
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as r:
            up_data = json.loads(r.read().decode("utf-8"))
            upload_url = up_data.get("response", {}).get("upload_url")
            
        if not upload_url:
            return False
            
        # 2. Upload file via multipart/form-data
        boundary = "----WebKitFormBoundary" + str(int(time.time()))
        body = []
        body.append(f"--{boundary}".encode("utf-8"))
        body.append(f'Content-Disposition: form-data; name="file"; filename="{p.name}"'.encode("utf-8"))
        body.append(b"Content-Type: application/octet-stream")
        body.append(b"")
        body.append(p.read_bytes())
        body.append(f"--{boundary}--".encode("utf-8"))
        body.append(b"")
        payload = b"\r\n".join(body)
        
        up_req = urllib.request.Request(
            upload_url,
            data=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
        )
        with urllib.request.urlopen(up_req, timeout=30, context=ssl_ctx) as up_r:
            up_res = json.loads(up_r.read().decode("utf-8"))
            file_blob = up_res.get("file")
            
        if not file_blob:
            return False
            
        # 3. Save doc
        save_url = f"https://api.vk.com/method/docs.save?file={urllib.parse.quote(file_blob)}&title={urllib.parse.quote(title or p.name)}&v={VK_API_VERSION}&access_token={token}"
        with urllib.request.urlopen(urllib.request.Request(save_url), timeout=10, context=ssl_ctx) as s_r:
            save_res = json.loads(s_r.read().decode("utf-8"))
            doc_info = save_res.get("response", {}).get("doc", {})
            owner_id = doc_info.get("owner_id")
            doc_id = doc_info.get("id")
            
        if owner_id and doc_id:
            attach = f"doc{owner_id}_{doc_id}"
            import random
            send_url = "https://api.vk.com/method/messages.send"
            send_data = {
                "peer_id": peer_id,
                "attachment": attach,
                "random_id": random.randint(1, 2147483647),
                "v": VK_API_VERSION,
                "access_token": token
            }
            req_s = urllib.request.Request(
                send_url,
                data=urllib.parse.urlencode(send_data).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            with urllib.request.urlopen(req_s, timeout=10, context=ssl_ctx) as fin_r:
                return True
    except Exception as e:
        print(f"[VK Doc Upload Error]: {e}")
    return False

def get_main_keyboard() -> dict:
    return {
        "one_time": False,
        "inline": False,
        "buttons": [
            [
                {"action": {"type": "text", "label": "🎯 Мои треки", "payload": "{\"cmd\":\"tracks\"}"}, "color": "primary"},
                {"action": {"type": "text", "label": "📚 Study Guide SVD", "payload": "{\"cmd\":\"study_svd\"}"}, "color": "positive"}
            ],
            [
                {"action": {"type": "text", "label": "⚡ Статус сервера", "payload": "{\"cmd\":\"status\"}"}, "color": "secondary"},
                {"action": {"type": "text", "label": "📥 Файлы INBOX", "payload": "{\"cmd\":\"inbox\"}"}, "color": "secondary"}
            ]
        ]
    }

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
            print(f"[VK] Сообщение отклонено (нет в белом списке): from_id={from_id}, peer_id={peer_id}")
            return

    # Resolve bound username
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

    clean_t = text.strip()
    cmd_lower = clean_t.lower()

    # 1. Login via password in VK (/login <pass>)
    if cmd_lower.startswith("/login ") or cmd_lower.startswith("логин "):
        pwd = clean_t.split(maxsplit=1)[1].strip()
        from core.auth_manager import authenticate_user, bind_vk_id_to_user
        auth_user = authenticate_user("ardont", pwd)
        target_u = "ardont" if auth_user else None
        if not auth_user:
            auth_user = authenticate_user("maxim", pwd)
            target_u = "maxim" if auth_user else None
            
        if auth_user and target_u:
            bind_vk_id_to_user(target_u, str(from_id))
            send_vk_message(peer_id, f"✅ Авторизация успешна! Ваш VK ID ({from_id}) привязан к аккаунту @{target_u} ({auth_user.get('display_name')}).", token)
            return
        else:
            send_vk_message(peer_id, "❌ Неверный пароль. Попробуйте: /login <пароль>", token)
            return

    # 2. View Tracks (/tracks)
    if cmd_lower in ["/tracks", "треки", "мои треки", "🎯 мои треки", "план учебы"]:
        from core.growth_tracker import load_user_tracks
        u_tracks = load_user_tracks(bound_user)
        tracks_list = u_tracks.get("tracks", [])
        
        reply_lines = [f"🎯 НАПРАВЛЕНИЯ РАЗВИТИЯ @{bound_user}:\n"]
        for t in tracks_list:
            reply_lines.append(f"📌 {t.get('title')} ({t.get('progress_percent', 0)}%)")
            reply_lines.append(f"   Фокус: {t.get('focus_area')}")
            for top in t.get('topics', [])[:3]:
                st = "✅" if top.get("completed") else "⏳"
                reply_lines.append(f"   {st} {top.get('name')}")
            reply_lines.append("")
            
        if u_tracks.get("daily_focus"):
            reply_lines.append(f"🔥 Фокус дня: {u_tracks.get('daily_focus')}")
            
        reply_lines.append("\n💡 Команды: `/study <тема>` — создать Study Guide, `/done <тема>` — отметить готовность.")
        send_vk_message(peer_id, "\n".join(reply_lines), token)
        return

    # 3. Quick Study Guide (/study <topic>)
    if cmd_lower.startswith("/study ") or cmd_lower.startswith("учеба ") or cmd_lower.startswith("/guide ") or cmd_lower == "📚 study guide svd":
        topic = clean_t.split(maxsplit=1)[1].strip() if len(clean_t.split(maxsplit=1)) > 1 and not cmd_lower.startswith("📚") else "Сингулярное разложение матриц (SVD) для ШАД"
        send_vk_message(peer_id, f"⏳ [NotebookLM] Генерирую подробный Study Guide по теме: '{topic}'... Пожалуйста, подождите.", token)
        from core.agent_tools import tool_notebooklm_synthesize
        guide_res = tool_notebooklm_synthesize(topic, format_type="study_guide")
        send_vk_message(peer_id, guide_res[:4000], token)
        return

    # 4. Mark Topic Done (/done <topic>)
    if cmd_lower.startswith("/done ") or cmd_lower.startswith("сделано "):
        topic_done = clean_t.split(maxsplit=1)[1].strip()
        from core.growth_tracker import mark_topic_completed
        ok, msg_done = mark_topic_completed(bound_user, "shad_math", topic_done)
        if not ok:
            ok, msg_done = mark_topic_completed(bound_user, "homeserver_dev", topic_done)
        send_vk_message(peer_id, msg_done, token)
        return

    # 5. Server Status (/status)
    if cmd_lower in ["/status", "статус", "сервер", "⚡ статус сервера"]:
        import psutil
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        send_vk_message(peer_id, f"⚡ [HomeServer 24/7 Статус]\n• CPU: {cpu}%\n• RAM: {ram}%\n• Авторизован: @{bound_user}\n• AI Ядро: OmniRoute + Google Gemini Flash Lite\n• Все службы активны!", token)
        return

    # Handle standard AI queries and attachments
    keyboard = get_main_keyboard()
    attached_info = []

    for att in attachments:
        att_type = att.get("type")
        if att_type == "doc":
            doc = att.get("doc", {})
            title = doc.get("title", "document")
            url = doc.get("url")
            if url:
                attached_info.append(f"Документ: {title} ({url})")
        elif att_type == "audio_message":
            audio = att.get("audio_message", {})
            link_ogg = audio.get("link_ogg") or audio.get("link_mp3")
            if link_ogg:
                try:
                    tmp_audio = INBOX_DIR / f"voice_{from_id}_{int(time.time())}.ogg"
                    urllib.request.urlretrieve(link_ogg, str(tmp_audio))
                    from core.audio_transcriber import transcribe_audio_file
                    tr = transcribe_audio_file(tmp_audio)
                    if tr.get("status") == "ok":
                        text = tr.get("text")
                        attached_info.append(f"[Голосовое сообщение расшифровано: {text}]")
                except Exception as e:
                    attached_info.append(f"[Ошибка расшифровки аудио: {e}]")

    query = text
    if attached_info:
        query += "\n\n" + "\n".join(attached_info)

    if not query.strip():
        send_vk_message(peer_id, "Привет! Я Джарвис — HomeServer AI Hub. Чем могу помочь?", token, keyboard)
        return

    try:
        from core.chat_agent import ask_chat_agent
        response = ask_chat_agent(query, username=bound_user, user_name=bound_user)
        ai_text = response.get("response") or response.get("reply") or "Готово."
        
        file_matches = re.findall(r'\[SEND_FILE:([^\]]+)\]', ai_text)
        clean_response = re.sub(r'\[SEND_FILE:[^\]]+\]', '', ai_text).strip()
        
        if clean_response:
            send_vk_message(peer_id, clean_response, token, keyboard)
            
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
        print("[VK Bot] Токен группы не задан. Бот отключен.")
        return

    print(f"[VK Bot] Запуск LongPoll сервера (allowed_user_id={allowed_user_id})...")
    
    while True:
        try:
            lp_url = f"https://api.vk.com/method/groups.getLongPollServer?group_id={group_id}&v={VK_API_VERSION}&access_token={token}"
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(urllib.request.Request(lp_url), timeout=10, context=ssl_ctx) as r:
                lp_data = json.loads(r.read().decode("utf-8"))
                
            resp = lp_data.get("response", {})
            server = resp.get("server")
            key = resp.get("key")
            ts = resp.get("ts")
            
            if not server or not key or not ts:
                print(f"[VK Bot] Ошибка получения LongPoll параметров. Повтор через 5с...")
                time.sleep(5)
                continue
                
            print(f"[VK Bot] LongPoll подключен успешно к {server}. Ожидание входящих сообщений...")
            
            while True:
                poll_url = f"{server}?act=a_check&key={key}&ts={ts}&wait=25"
                try:
                    with urllib.request.urlopen(urllib.request.Request(poll_url), timeout=35, context=ssl_ctx) as pr:
                        events_data = json.loads(pr.read().decode("utf-8"))
                except Exception:
                    continue
                    
                if "failed" in events_data:
                    failed_code = events_data.get("failed")
                    if failed_code == 1:
                        ts = events_data.get("ts")
                    else:
                        break
                    continue
                    
                ts = events_data.get("ts", ts)
                updates = events_data.get("updates", [])
                
                for upd in updates:
                    upd_type = upd.get("type")
                    if upd_type == "message_new":
                        obj = upd.get("object", {})
                        handle_vk_event(obj, token, allowed_user_id)
        except Exception as e:
            print(f"[VK Bot Critical Loop Error]: {e}. Перезапуск через 5 сек...")
            time.sleep(5)

def start_vk_bot_thread():
    """Запускает VK Bot polling в отдельном фоновом потоке."""
    import threading
    t = threading.Thread(target=run_vk_bot_polling, daemon=True, name="VKBotThread")
    t.start()
    print("[VK Bot] Фоновый поток запущен.")
    return t

if __name__ == "__main__":
    run_vk_bot_polling()
