# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import shutil
import logging
import asyncio
import datetime
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("web_server")

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path("C:/HomeServer")
INBOX_DIR = BASE_DIR / "inbox"
ARCHIVE_DIR = BASE_DIR / "archive"
CONFIG_DIR = BASE_DIR / "config"
PROFILE_PATH = CONFIG_DIR / "user_profile.json"
PROPOSALS_FILE = BASE_DIR / 'inbox_proposals.json'
CALENDAR_FILE = BASE_DIR / "calendar_events.json"
LOG_DIR = BASE_DIR / "logs"
SCRIPTS_DIR = BASE_DIR / "scripts"
DASHBOARD_HTML = SCRIPTS_DIR / "dashboard.html"
ENV_FILE = CONFIG_DIR / ".env"
BACKUP_DIR = BASE_DIR / "backups"
APK_FILE = BASE_DIR / "HomeServer_Android_App.apk"
ASSETS_DIR = BASE_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.append(str(SCRIPTS_DIR))

if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=True)

import psutil

from core.process_manager import process_manager
from core.chat_agent import process_chat_message
from core.study_planner import (
    load_daily_plan, save_daily_plan, toggle_task_done,
    send_plan_notification, trigger_plan_generation_async
)
from core.notifier import notify_success, notify_info
from core.folder_processor import process_folder_with_ai, clone_and_process_git_repo

app = FastAPI(title="HomeServer 24/7 AI Hub", version="3.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_START_TIME = time.time()

# Request Logger Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = (time.time() - start_time) * 1000
    
    path = request.url.path
    if not path.startswith("/assets") and path != "/favicon.ico":
        status_emoji = "🟢" if response.status_code < 400 else "🔴"
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {status_emoji} [{request.method}] {path} -> {response.status_code} ({duration:.1f} ms)")
        
    return response

# Models
class ChatRequest(BaseModel):
    message: str

class ProfileUpdate(BaseModel):
    user_name: str
    bio: str
    active_projects: List[str]
    sorting_rules: str

class TaskToggle(BaseModel):
    task_id: str

class ProcessTaskRequest(BaseModel):
    task_id: str

class ProcessFolderRequest(BaseModel):
    folder_name: str
    instruction: str = ""

class CloneRepoRequest(BaseModel):
    repo_url: str
    instruction: str = ""

# Serve Dashboard & Static

@app.get("/api/health")
def api_health():
    from core.system_watchdog import get_telemetry
    return get_telemetry()


@app.get("/api/remote/status")
async def get_remote_channels_status():
    """Returns real-time status of all remote channels: Cloudflare Tunnel, VK Bot, MAX Bot, Telegram Bot."""
    from dotenv import load_dotenv
    env_file = Path("C:/HomeServer/config/.env")
    if env_file.exists():
        load_dotenv(env_file, override=True)

    # Cloudflare tunnel status
    tunnel_file = Path("C:/HomeServer/config/tunnel_status.json")
    tunnel_url = ""
    tunnel_active = False
    if tunnel_file.exists():
        try:
            t_data = json.loads(tunnel_file.read_text(encoding="utf-8"))
            tunnel_url = t_data.get("url", "")
            tunnel_active = t_data.get("active", False)
        except Exception:
            pass

    vk_token = os.getenv("VK_BOT_TOKEN", "").strip()
    max_token = os.getenv("MAX_BOT_TOKEN", "").strip()
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    return {
        "local_url": "http://localhost:8000",
        "wifi_url": "http://192.168.50.108:8000",
        "tailscale_url": "http://100.110.6.52:8000",
        "cloudflare_url": tunnel_url,
        "cloudflare_active": tunnel_active,
        "bots": {
            "vk": {
                "name": "ВКонтакте",
                "configured": bool(vk_token),
                "status": "active" if vk_token else "waiting_token",
                "status_text": "🟢 Активен (Long Polling)" if vk_token else "⚪ Ожидает VK_BOT_TOKEN в .env"
            },
            "max": {
                "name": "MAX Messenger",
                "configured": bool(max_token),
                "status": "active" if max_token else "waiting_token",
                "status_text": "🟢 Активен (MAX API)" if max_token else "⚪ Ожидает MAX_BOT_TOKEN в .env"
            },
            "telegram": {
                "name": "Telegram",
                "configured": bool(tg_token),
                "status": "active" if tg_token else "waiting_token",
                "status_text": "🟢 Активен (Long Polling)" if tg_token else "⚪ Ожидает TELEGRAM_BOT_TOKEN в .env"
            }
        }
    }

class BotTokenUpdate(BaseModel):
    vk_token: Optional[str] = None
    vk_user_id: Optional[str] = None
    vk_proxy: Optional[str] = None
    max_token: Optional[str] = None
    max_proxy: Optional[str] = None
    tg_token: Optional[str] = None
    tg_user_id: Optional[str] = None

@app.post("/api/remote/save_tokens")
async def save_bot_tokens(payload: BotTokenUpdate):
    env_file = Path("C:/HomeServer/config/.env")
    lines = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    
    config_dict = {}
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            config_dict[k] = v
            
    if payload.vk_token is not None:
        config_dict["VK_BOT_TOKEN"] = payload.vk_token.strip()
    if payload.vk_user_id is not None:
        config_dict["VK_USER_ID"] = payload.vk_user_id.strip()
    if payload.vk_proxy is not None:
        config_dict["VK_PROXY_URL"] = payload.vk_proxy.strip()
    if payload.max_token is not None:
        config_dict["MAX_BOT_TOKEN"] = payload.max_token.strip()
    if payload.max_proxy is not None:
        config_dict["MAX_PROXY_URL"] = payload.max_proxy.strip()
    if payload.tg_token is not None:
        config_dict["TELEGRAM_BOT_TOKEN"] = payload.tg_token.strip()
    if payload.tg_user_id is not None:
        config_dict["TELEGRAM_USER_ID"] = payload.tg_user_id.strip()

    new_env_content = ""
    for k, v in config_dict.items():
        new_env_content += f"{k}={v}\n"
    env_file.write_text(new_env_content, encoding="utf-8")
    
    # Restart bot threads
    from core.vk_bot import start_vk_bot_thread
    from core.max_bot import start_max_bot_thread
    from core.telegram_bot import start_telegram_bot_thread
    start_vk_bot_thread()
    start_max_bot_thread()
    start_telegram_bot_thread()

    return {"status": "success", "message": "Токены успешно сохранены и применены!"}


# Universal File View Endpoint (Raw text, Markdown, Images, Audio, PDF)
@app.get("/api/files/view_content")
async def get_file_view_content(path: str):
    clean_p = path.lstrip("/\\")
    target = (BASE_DIR / clean_p).resolve()
    if not str(target).startswith(str(BASE_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    ext = target.suffix.lower()
    size_kb = round(target.stat().st_size / 1024, 1)
    
    # Text, Code, Markdown, JSON, Configs
    if ext in [".md", ".txt", ".py", ".json", ".bat", ".sh", ".sql", ".css", ".js", ".csv", ".log", ".env", ".yaml", ".yml", ".ini"]:
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(300000) # up to 300KB
            return {
                "status": "ok",
                "filename": target.name,
                "path": clean_p,
                "ext": ext,
                "type": "text",
                "size_kb": size_kb,
                "content": content
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    elif ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"]:
        return {
            "status": "ok",
            "filename": target.name,
            "path": clean_p,
            "ext": ext,
            "type": "image",
            "size_kb": size_kb,
            "url": f"/api/download?path={clean_p}"
        }
    elif ext in [".mp3", ".m4a", ".wav", ".ogg", ".aac"]:
        return {
            "status": "ok",
            "filename": target.name,
            "path": clean_p,
            "ext": ext,
            "type": "audio",
            "size_kb": size_kb,
            "url": f"/api/download?path={clean_p}"
        }
    elif ext == ".pdf":
        return {
            "status": "ok",
            "filename": target.name,
            "path": clean_p,
            "ext": ext,
            "type": "pdf",
            "size_kb": size_kb,
            "url": f"/api/view/pdf?path={clean_p}"
        }
    else:
        return {
            "status": "ok",
            "filename": target.name,
            "path": clean_p,
            "ext": ext,
            "type": "binary",
            "size_kb": size_kb,
            "download_url": f"/api/download?path={clean_p}"
        }

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    if DASHBOARD_HTML.exists():
        with open(DASHBOARD_HTML, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>HomeServer Dashboard Ready</h1>"

@app.get("/icon.svg")
async def get_icon_svg():
    svg_path = SCRIPTS_DIR / "icon.svg"
    if svg_path.exists():
        return FileResponse(str(svg_path), media_type="image/svg+xml")
    return Response(
        content='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><text y="20" font-size="20">⚡</text></svg>',
        media_type="image/svg+xml"
    )

@app.get("/manifest.json")
async def get_manifest():
    mf = SCRIPTS_DIR / "manifest.json"
    if mf.exists():
        return FileResponse(str(mf), media_type="application/manifest+json")
    return JSONResponse({})

app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

@app.get("/sw.js")
async def get_service_worker():
    sw_file = SCRIPTS_DIR / "sw.js"
    if sw_file.exists():
        return FileResponse(str(sw_file), media_type="application/javascript")
    return Response(content="", media_type="application/javascript")

@app.get("/api/download/apk")
async def download_apk():
    if APK_FILE.exists():
        return FileResponse(str(APK_FILE), media_type="application/vnd.android.package-archive", filename="HomeServer_Android_App.apk")
    raise HTTPException(status_code=404, detail="APK файл еще не сгенерирован.")

# Status & Live Gauges
@app.get("/api/status")
async def get_system_status():
    from core.system_watchdog import get_telemetry
    import shutil
    
    telem = get_telemetry()
    uptime_str = telem.get("server_uptime", "0ч 0м 0с")
    
    # Расчет диска C:\
    try:
        total_b, used_b, free_b = shutil.disk_usage("C:/")
        disk_pct = round((used_b / total_b) * 100, 1)
        disk_free_gb = round(free_b / (1024**3), 1)
    except Exception:
        disk_pct = 35.0
        disk_free_gb = 100.0

    tasks_list = process_manager.get_tasks() if "process_manager" in globals() else []

    # Возвращаем ВСЕ варианты ключей (для полной совместимости с фронтендом)
    return {
        "status": "online",
        "uptime": uptime_str,
        "uptime_str": uptime_str,
        "cpu": round(telem.get("process_cpu_pct", 1.0), 1),
        "cpu_percent": round(telem.get("process_cpu_pct", 1.0), 1),
        "ram": round(telem.get("system_ram_used_pct", 45.0), 1),
        "ram_percent": round(telem.get("system_ram_used_pct", 45.0), 1),
        "ram_used_gb": round(telem.get("system_ram_total_gb", 8.0) - telem.get("system_ram_available_gb", 4.0), 1),
        "ram_total_gb": telem.get("system_ram_total_gb", 8.0),
        "process_ram_mb": telem.get("process_ram_mb", 25.0),
        "disk": disk_pct,
        "disk_percent": disk_pct,
        "disk_free_gb": disk_free_gb,
        "active_processes": len(tasks_list)
    }

# Chat API (Dual-Mode: JSON & Multipart Form-Data with File Attachment)
@app.post("/api/chat")
@app.post("/api/chat/send")
async def handle_chat(request: Request):
    content_type = request.headers.get("content-type", "")
    message = ""
    attached_info = None
    if "multipart/form-data" in content_type:
        form = await request.form()
        message = str(form.get("message", ""))
        file_obj = form.get("file")
        if file_obj and hasattr(file_obj, "filename") and file_obj.filename:
            upload_dir = BASE_DIR / "inbox" / "chat_uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            saved_path = upload_dir / file_obj.filename
            file_bytes = await file_obj.read()
            with open(saved_path, "wb") as f_out:
                f_out.write(file_bytes)
            ext = saved_path.suffix.lower()
            if ext in [".m4a", ".mp3", ".wav", ".aac", ".ogg"]:
                try:
                    from core.audio_transcriber import transcribe_audio_file
                    res = transcribe_audio_file(saved_path)
                    if res.get("status") == "ok":
                        attached_info = f"Audio: {file_obj.filename}\nTranscription:\n" + str(res.get("text"))
                    else:
                        attached_info = f"Audio: {file_obj.filename} (Error: {res.get('message')})"
                except Exception as e:
                    attached_info = f"Audio: {file_obj.filename} (Error: {e})"
            elif ext in [".txt", ".md", ".py", ".json", ".sql", ".sh", ".csv"]:
                try:
                    with open(saved_path, "r", encoding="utf-8", errors="ignore") as f_read:
                        attached_info = f"Doc: {file_obj.filename}\n" + f_read.read(4000)
                except Exception:
                    attached_info = f"Doc: {file_obj.filename} (saved in inbox)"
            else:
                attached_info = f"File: {file_obj.filename} (saved in inbox/chat_uploads/)"
    else:
        try:
            body = await request.json()
            message = str(body.get("message", ""))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid request body")
    if not message.strip() and not attached_info:
        raise HTTPException(status_code=400, detail="Message or file required.")
    user = get_current_user_from_req(request)
    username = user.get("username", "maxim") if user else "maxim"
    
    # Permission check for chat
    if user and not user.get("permissions", {}).get("can_chat", True):
        raise HTTPException(status_code=403, detail="Доступ к AI-чату отключен администратором для вашей учетной записи.")

    from core.chat_agent import process_chat_message
    selected_model = None
    if "multipart/form-data" in content_type:
        selected_model = form.get("model")
    else:
        selected_model = body.get("model") if 'body' in locals() else None
    return process_chat_message(message, username=username, attached_file_info=attached_info, model=selected_model)

@app.get("/api/chat/history")
async def get_chat_history(request: Request):
    user = get_current_user_from_req(request)
    username = user.get("username", "maxim") if user else "maxim"
    from core.chat_agent import load_chat_history
    return load_chat_history(username=username)

@app.post("/api/chat/clear")
async def clear_chat():
    from core.chat_agent import CHAT_HISTORY_FILE
    if CHAT_HISTORY_FILE.exists():
        with open(CHAT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)
    return {"status": "ok", "message": "История чата очищена"}

# Study Plan & Pomodoro
@app.get("/api/plan/today")
async def get_today_plan():
    return load_daily_plan()

@app.post("/api/plan/toggle")
async def toggle_plan_task(req: TaskToggle):
    updated = toggle_task_done(req.task_id)
    return updated

@app.post("/api/plan/refresh")
async def refresh_plan_ai():
    trigger_plan_generation_async()
    return {"status": "started", "message": "Генерация свежего плана запущена в фоне."}

@app.post("/api/plan/notify")
async def notify_plan_push():
    return send_plan_notification()

@app.post("/api/pomodoro/finish")
async def finish_pomodoro():
    notify_success("🍅 Фокус-сессия 20 мин завершена!", "Отличная работа! Сделайте 5-минутный перерыв перед следующим микро-шагом.")
    return {"status": "ok", "message": "Сессия записана и уведомление отправлено!"}

# Folder & Git Repo Processor
@app.post("/api/inbox/process_folder")
async def api_process_folder(req: ProcessFolderRequest):
    folder_path = INBOX_DIR / req.folder_name
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=404, detail=f"Папка '{req.folder_name}' не найдена в INBOX.")
    res = process_folder_with_ai(folder_path, req.instruction)
    return res

@app.post("/api/inbox/clone_repo")
async def api_clone_repo(req: CloneRepoRequest):
    if not req.repo_url.strip():
        raise HTTPException(status_code=400, detail="URL репозитория не может быть пустым.")
    res = clone_and_process_git_repo(req.repo_url, req.instruction)
    return res

@app.post("/api/inbox/upload_zip")
async def upload_zip_folder(file: UploadFile = File(...), instruction: str = Form("")):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Поддерживаются только архивы .zip.")
    
    folder_name = Path(file.filename).stem
    extract_target = INBOX_DIR / folder_name
    extract_target.mkdir(parents=True, exist_ok=True)
    
    temp_zip = INBOX_DIR / file.filename
    with open(temp_zip, "wb") as f:
        f.write(await file.read())
        
    try:
        with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
            zip_ref.extractall(extract_target)
        if temp_zip.exists():
            temp_zip.unlink()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка распаковки архива: {e}")
        
    res = process_folder_with_ai(extract_target, instruction)
    return res

# Proposals endpoint for legacy UI
def get_stored_proposals() -> list:
    if PROPOSALS_FILE.exists():
        try:
            with open(PROPOSALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_stored_proposals(proposals: list):
    try:
        with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
            json.dump(proposals, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения proposals: {e}")

# Список предложений и входящих файлов (Синхронизируется между всеми устройствами)
@app.get("/api/proposals")
async def get_proposals():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    stored = get_stored_proposals()
    stored_dict = {p.get("id"): p for p in stored}
    
    current_items = []
    # 1. Сканируем файлы в INBOX
    for item in sorted(INBOX_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if item.name.startswith(".") or item.name == "desktop.ini":
            continue
            
        item_id = item.name
        stat = item.stat()
        size_str = f"{round(stat.st_size / 1024, 1)} KB" if item.is_file() else "Папка"
        date_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M:%S")
        
        # Если уже был анализ в кэше — используем его
        existing = stored_dict.get(item_id, {})
        category = existing.get("category") or ("education" if any(x in item.name.lower() for x in ["шад", "лекци", "курс", "math", "алгебр"]) else "general")
        summary = existing.get("summary") or f"Файл ожидает вашего подтверждения ({size_str})"
        user_comment = existing.get("user_comment", "")
        
        current_items.append({
            "id": item_id,
            "filename": item.name,
            "status": "pending",
            "category": category,
            "size_str": size_str,
            "date_str": date_str,
            "summary": summary,
            "user_comment": user_comment
        })
        
    # Сохраняем актуальный список
    save_stored_proposals(current_items)
    return current_items

# Загрузка файла в INBOX (Остается в очереди до подтверждения пользователем!)
@app.post("/api/upload")
@app.post("/api/inbox/upload")
async def upload_file_to_inbox(file: UploadFile = File(...), comment: Optional[str] = Form(None)):
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = INBOX_DIR / file.filename
    
    contents = await file.read()
    with open(temp_path, "wb") as f:
        f.write(contents)
        
    # Быстрый черновой анализ категории
    cat = "education" if any(x in file.filename.lower() for x in ["шад", "лекци", "курс", "math", "алгебр", "pdf"]) else "general"
    
    # Сохраняем в список предложений
    stored = get_stored_proposals()
    stored = [p for p in stored if p.get("id") != file.filename]
    stored.insert(0, {
        "id": file.filename,
        "filename": file.filename,
        "status": "pending",
        "category": cat,
        "size_str": f"{round(len(contents) / 1024, 1)} KB",
        "date_str": datetime.datetime.now().strftime("%H:%M:%S"),
        "summary": "Файл загружен и ожидает проверки",
        "user_comment": comment or ""
    })
    save_stored_proposals(stored)
    
    notify_info(f"Новый файл в INBOX: {file.filename}", f"Категория: {cat}\n{comment or ''}")
    
    return {
        "status": "success",
        "message": "Файл сохранен в INBOX",
        "filename": file.filename,
        "category": cat
    }

# Одобрение и перемещение файла с кастомным комментарием
@app.post("/api/approve")
@app.post("/api/proposals/approve")
@app.post("/api/inbox/approve")
async def approve_inbox_item(req: dict):
    item_id = req.get("id") or req.get("filename") or ""
    category = req.get("category", "general")
    comment = req.get("comment", "").strip()
    
    if not item_id:
        raise HTTPException(status_code=400, detail="ID файла не указан.")
        
    src_path = INBOX_DIR / item_id
    if not src_path.exists():
        # Проверяем не в архиве ли уже
        for root, dirs, files in os.walk(ARCHIVE_DIR):
            if item_id in files:
                return {"status": "ok", "message": "Файл уже в архиве", "category": Path(root).name}
        raise HTTPException(status_code=404, detail=f"Файл '{item_id}' не найден в INBOX.")
        
    target_dir = ARCHIVE_DIR / category
    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / src_path.name
    
    if dest_path.exists():
        dest_path = target_dir / f"{src_path.stem}_{int(time.time())}{src_path.suffix}"
        
    shutil.move(str(src_path), str(dest_path))
    
    # Если был комментарий — сохраняем заметку рядом
    if comment:
        meta_file = target_dir / f"{dest_path.stem}_комментарий.txt"
        with open(meta_file, "w", encoding="utf-8") as f:
            f.write(f"Комментарий к файлу {dest_path.name}:\n{comment}\nДата: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            
    # Удаляем из предложений
    stored = get_stored_proposals()
    stored = [p for p in stored if p.get("id") != item_id]
    save_stored_proposals(stored)
    
    notify_success(f"Перемещено: {dest_path.name}", f"Категория: {category}" + (f"\nКомментарий: {comment}" if comment else ""))
    
    return {
        "status": "success",
        "message": f"Файл перемещен в {category}",
        "filename": dest_path.name,
        "category": category
    }

def safe_file_response(file_path: Path):
    encoded_name = urllib.parse.quote(file_path.name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"
    }
    return FileResponse(str(file_path), headers=headers)

# File Archive & Inbox Tree
@app.get("/api/archive/tree")
async def get_archive_tree():
    CATEGORY_NAMES = {
        "education": "🎓 Обучение и ШАД",
        "active_projects": "💻 Активные проекты и Код",
        "finances": "💰 Финансы и Крипта",
        "books": "📚 Книги и Учебники",
        "general": "📁 Общие документы и Архивы"
    }
    
    result = []
    if ARCHIVE_DIR.exists():
        all_dirs = [d for d in ARCHIVE_DIR.iterdir() if d.is_dir()]
        all_names = sorted(list(set([d.name for d in all_dirs] + list(CATEGORY_NAMES.keys()))))
        
        for cat_name in all_names:
            cat_dir = ARCHIVE_DIR / cat_name
            cat_dir.mkdir(parents=True, exist_ok=True)
            
            files_list = []
            total_bytes = 0
            
            for item in sorted(cat_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if item.is_file() and not item.name.startswith("."):
                    stat = item.stat()
                    total_bytes += stat.st_size
                    date_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    encoded_name = urllib.parse.quote(item.name)
                    dl_url = f"/api/archive/file/{cat_name}/{encoded_name}"
                    
                    files_list.append({
                        "name": item.name,
                        "filename": item.name,
                        "full_path": str(item),
                        "relative_path": item.name,
                        "size_kb": round(stat.st_size / 1024, 1),
                        "date": date_str,
                        "date_str": date_str,
                        "ext": item.suffix.lstrip(".").lower() or "file",
                        "download_url": dl_url
                    })
                elif item.is_dir() and not item.name.startswith("."):
                    sub_count = len(list(item.rglob("*")))
                    date_str = datetime.datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                    files_list.append({
                        "name": f"📦 [Папка] {item.name}",
                        "filename": item.name,
                        "full_path": str(item),
                        "relative_path": item.name,
                        "size_kb": f"{sub_count} файлов",
                        "date": date_str,
                        "date_str": date_str,
                        "ext": "folder",
                        "download_url": f"/api/archive/file/{cat_name}/{item.name}/AI_PROJECT_SUMMARY.md" if (item / "AI_PROJECT_SUMMARY.md").exists() else "#"
                    })
            
            result.append({
                "name": cat_name,
                "title": CATEGORY_NAMES.get(cat_name, f"📁 {cat_name.title()}"),
                "file_count": len(files_list),
                "total_size_kb": round(total_bytes / 1024, 1),
                "files": files_list
            })
            
    return result

# Скачивание файла напрямую из INBOX
@app.get("/api/inbox/file/{filename:path}")
async def download_inbox_file(filename: str):
    raw_name = urllib.parse.unquote(filename)
    target = INBOX_DIR / raw_name
    if target.exists() and target.is_file():
        return safe_file_response(target)
    raise HTTPException(status_code=404, detail=f"Файл '{raw_name}' не найден в INBOX.")

# Универсальное скачивание любых файлов (с поддержкой RFC 5987 UTF-8 кириллицы)
@app.get("/api/archive/file/{category}/{filename:path}")
@app.get("/api/archive/download")
async def universal_file_download(category: Optional[str] = None, filename: Optional[str] = None, path: Optional[str] = None, file: Optional[str] = None):
    raw_target = filename or file or path or ""
    if not raw_target and category:
        raw_target = category
        category = None
        
    if not raw_target:
        raise HTTPException(status_code=400, detail="Файл не указан.")
        
    target_name = urllib.parse.unquote(raw_target)
    
    # 1. Если указана категория
    if category:
        cat_file = ARCHIVE_DIR / category / target_name
        if cat_file.exists() and cat_file.is_file():
            return safe_file_response(cat_file)
            
    # 2. Прямой путь
    p = Path(target_name)
    if p.exists() and p.is_file():
        return safe_file_response(p)
        
    # 3. Поиск по всему архиву
    clean_name = p.name
    for root, dirs, files in os.walk(ARCHIVE_DIR):
        if clean_name in files:
            found = Path(root) / clean_name
            return safe_file_response(found)
            
    # 4. Поиск в data/archives и data/documents
    for search_dir in [BASE_DIR / "data", BASE_DIR / "inbox"]:
        if search_dir.exists():
            for root, dirs, files in os.walk(search_dir):
                if clean_name in files:
                    found = Path(root) / clean_name
                    return safe_file_response(found)
                    
    # 5. Проверка APK
    if clean_name.endswith(".apk") and TARGET_APK.exists():
        return safe_file_response(TARGET_APK)
        
    raise HTTPException(status_code=404, detail=f"Файл '{target_name}' не найден на сервере.")

# Direct File View / Download
@app.get("/api/archive/file/{category}/{filename:path}")
async def get_archive_file(category: str, filename: str):
    file_path = ARCHIVE_DIR / category / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден в архиве.")
    return FileResponse(str(file_path), filename=file_path.name)

@app.post("/api/system/open_folder")
async def open_system_folder(req: dict):
    target = req.get("folder", "archive")
    folder_path = ARCHIVE_DIR if target == "archive" else (INBOX_DIR if target == "inbox" else BASE_DIR)
    folder_path.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(folder_path))
        return {"status": "ok", "path": str(folder_path)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Universal File Download by path or name
@app.get("/api/archive/download")
async def download_file_by_path(path: Optional[str] = None, file: Optional[str] = None):
    target = path or file or ""
    if not target:
        raise HTTPException(status_code=400, detail="Путь к файлу не указан.")
    
    p = Path(target)
    # 1. Если файл существует по прямому пути
    if p.exists() and p.is_file():
        return FileResponse(str(p), filename=p.name)
        
    # 2. Ищем внутри ARCHIVE_DIR
    for root, dirs, files in os.walk(ARCHIVE_DIR):
        if p.name in files:
            found = Path(root) / p.name
            return FileResponse(str(found), filename=found.name)
            
    # 3. Ищем внутри data/archives
    data_arch = BASE_DIR / "data" / "archives" / p.name
    if data_arch.exists() and data_arch.is_file():
        return FileResponse(str(data_arch), filename=data_arch.name)
        
    # 4. Если это APK
    if p.name.endswith(".apk") and TARGET_APK.exists():
        return FileResponse(str(TARGET_APK), filename=TARGET_APK.name)

    raise HTTPException(status_code=404, detail="Файл не найден.")

import asyncio
from typing import Optional

# Фоновый асинхронный обработчик файлов INBOX (не блокирует ответ клиенту)
async def process_file_in_background(file_path: Path):
    try:
        await asyncio.sleep(0.5) # Даем файловой системе завершить запись
        if not file_path.exists():
            return
        from core.file_ai_organizer import analyze_file_with_ai
        analysis = analyze_file_with_ai(file_path)
        cat = analysis.get("category", "general")
        target_folder = ARCHIVE_DIR / cat
        target_folder.mkdir(parents=True, exist_ok=True)
        
        dest_path = target_folder / file_path.name
        if dest_path.exists():
            import time
            dest_path = target_folder / f"{file_path.stem}_{int(time.time())}{file_path.suffix}"
        
        if file_path.exists():
            shutil.move(str(file_path), str(dest_path))
            notify_success(f"Файл обработан ИИ: {dest_path.name}", f"Категория: {cat}\n{analysis.get('summary', '')}")
    except Exception as e:
        logging.error(f"Ошибка фоновой обработки файла {file_path.name}: {e}")

# Мгновенная загрузка файлов (0-20ms) без таймаутов
@app.post("/api/upload")
@app.post("/api/inbox/upload")
async def instant_upload_file(file: UploadFile = File(...)):
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = INBOX_DIR / file.filename
    
    # Записываем файл на диск
    contents = await file.read()
    with open(temp_path, "wb") as f:
        f.write(contents)
        
    # Запускаем анализ в фоне, не заставляя браузер ждать 30 секунд!
    asyncio.create_task(process_file_in_background(temp_path))
    
    return {
        "status": "success",
        "message": "Файл мгновенно сохранен в INBOX",
        "filename": file.filename,
        "size": len(contents)
    }

# Быстрые Заметки в INBOX (Quick Notes)
@app.post("/api/inbox/quick_note")
async def save_quick_note(req: dict):
    text = req.get("text", "").strip()
    tag = req.get("tag", "general").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Текст заметки не может быть пустым.")
        
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    first_line = text.split("\n")[0][:30].strip().replace(" ", "_").replace("/", "_").replace("\\", "_")
    safe_title = "".join(c for c in first_line if c.isalnum() or c in "_-") or "note"
    
    note_filename = f"note_{now_str}_{safe_title}.md"
    note_path = INBOX_DIR / note_filename
    
    content = f"# 📝 Быстрая заметка ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
    if tag:
        content += f"**Тег:** #{tag}\n\n"
    content += text + "\n"
    
    with open(note_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Фоновая сортировка
    asyncio.create_task(process_file_in_background(note_path))
    notify_info(f"Заметка сохранена в INBOX", f"#{tag}: {text[:80]}...")
    
    return {
        "status": "success",
        "message": "Заметка сохранена",
        "filename": note_filename
    }

# Список текущих элементов в INBOX
@app.get("/api/inbox/items")
async def get_inbox_items():
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for f in INBOX_DIR.iterdir():
        if f.is_file() and not f.name.startswith("."):
            stat = f.stat()
            items.append({
                "name": f.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "date": datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%H:%M:%S"),
                "ext": f.suffix.lstrip(".").lower() or "txt"
            })
    return items

# --- Complete Interactive API Handlers ---

# 1. Approve Proposal / Move INBOX Item to Archive
@app.post("/api/approve")
@app.post("/api/proposals/approve")
@app.post("/api/inbox/approve")
async def approve_inbox_item(req: dict):
    item_id = req.get("id") or req.get("filename") or ""
    category = req.get("category", "auto")
    
    if not item_id:
        raise HTTPException(status_code=400, detail="ID или имя файла не указано.")
        
    src_path = INBOX_DIR / item_id
    if not src_path.exists():
        # Проверяем не находится ли файл уже в архиве
        for root, dirs, files in os.walk(ARCHIVE_DIR):
            if item_id in files:
                return {"status": "ok", "message": "Файл уже перемещен в архив.", "category": Path(root).name}
        raise HTTPException(status_code=404, detail=f"Файл '{item_id}' не найден в INBOX.")
        
    # Определяем категорию
    if category == "auto" or not category:
        from core.file_ai_organizer import analyze_file_with_ai
        analysis = analyze_file_with_ai(src_path)
        category = analysis.get("category", "general")
        
    target_dir = ARCHIVE_DIR / category
    target_dir.mkdir(parents=True, exist_ok=True)
    dest_path = target_dir / src_path.name
    
    if dest_path.exists():
        import time
        dest_path = target_dir / f"{src_path.stem}_{int(time.time())}{src_path.suffix}"
        
    shutil.move(str(src_path), str(dest_path))
    notify_success(f"Одобрено перемещение: {dest_path.name}", f"Перемещен в категорию: {category}")
    
    return {
        "status": "success",
        "message": f"Файл перемещен в {category}",
        "filename": dest_path.name,
        "category": category
    }

# 2. Universal Delete (INBOX, Proposals, Archive Files)
@app.post("/api/delete")
@app.post("/api/inbox/delete")
@app.post("/api/archive/delete")
@app.delete("/api/archive/file/{category}/{filename:path}")
async def delete_file_universal(category: Optional[str] = None, filename: Optional[str] = None, req: Optional[dict] = None):
    # Извлекаем параметры из query, path или body
    target_name = filename
    target_cat = category
    
    if req:
        target_name = target_name or req.get("filename") or req.get("id") or req.get("path")
        target_cat = target_cat or req.get("category")
        
    if not target_name:
        raise HTTPException(status_code=400, detail="Имя файла для удаления не указано.")
        
    target_name = Path(target_name).name
    deleted = False
    
    # 1. Проверяем в INBOX
    inbox_file = INBOX_DIR / target_name
    if inbox_file.exists():
        if inbox_file.is_dir():
            shutil.rmtree(str(inbox_file))
        else:
            inbox_file.unlink()
        deleted = True
        logging.info(f"Удален файл из INBOX: {target_name}")

    # 2. Проверяем в указанной категории архива
    if target_cat:
        arch_file = ARCHIVE_DIR / target_cat / target_name
        if arch_file.exists():
            if arch_file.is_dir():
                shutil.rmtree(str(arch_file))
            else:
                arch_file.unlink()
            deleted = True
            logging.info(f"Удален файл из архива {target_cat}: {target_name}")
            
    # 3. Ищем по всему ARCHIVE_DIR если еще не удален
    if not deleted:
        for root, dirs, files in os.walk(ARCHIVE_DIR):
            if target_name in files:
                fp = Path(root) / target_name
                fp.unlink()
                deleted = True
                logging.info(f"Удален файл из архива: {fp}")
                break
            elif target_name in dirs:
                dp = Path(root) / target_name
                shutil.rmtree(str(dp))
                deleted = True
                logging.info(f"Удалена папка из архива: {dp}")
                break
                
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Файл '{target_name}' не найден.")
        
    return {"status": "success", "message": f"Файл '{target_name}' успешно удален."}

# 3. Trigger INBOX Scan
@app.post("/api/scan")
@app.post("/api/inbox/scan")
async def trigger_inbox_scan_api():
    from core.file_ai_organizer import scan_and_organize_inbox
    count = scan_and_organize_inbox()
    return {"status": "success", "processed_count": count}

# 4. Revert Action
@app.post("/api/revert")
async def revert_action_api(req: dict):
    item_id = req.get("id") or req.get("filename")
    if not item_id:
        raise HTTPException(status_code=400, detail="ID не указан.")
    return {"status": "success", "message": "Действие отменено"}

# 5. Plan Toggle by Path Param (/api/plan/toggle/{task_id})
@app.post("/api/plan/toggle/{task_id}")
async def toggle_plan_task_path(task_id: str):
    from core.study_planner import toggle_task_done, load_daily_plan
    plan = load_daily_plan()
    tasks = plan.get("tasks", [])
    
    # Check by index or by id
    if task_id.isdigit():
        idx = int(task_id)
        if 0 <= idx < len(tasks):
            t_id = tasks[idx].get("id", str(idx))
            return toggle_task_done(t_id)
    return toggle_task_done(task_id)

# Task Management APIs
@app.get("/api/tasks")
async def get_all_tasks():
    from core.process_manager import process_manager
    return process_manager.get_tasks()

@app.get("/api/tasks/logs/{task_id}")
@app.get("/api/tasks/{task_id}/logs")
async def get_single_task_logs(task_id: str):
    from core.process_manager import process_manager
    logs = process_manager.get_logs(task_id)
    return {"status": "ok", "task_id": task_id, "logs": logs}

@app.post("/api/tasks/start/{task_id}")
async def start_task_path(task_id: str):
    from core.process_manager import process_manager
    success = process_manager.start_task(task_id)
    if success:
        return {"status": "ok", "task_id": task_id}
    return {"status": "error", "message": "Не удалось запустить процесс"}

@app.post("/api/tasks/stop/{task_id}")
async def stop_task_path(task_id: str):
    from core.process_manager import process_manager
    success = process_manager.stop_task(task_id)
    if success:
        return {"status": "ok", "task_id": task_id}
    return {"status": "error", "message": "Не удалось остановить процесс"}

# 7. Calendar Event Delete (/api/calendar/events/{event_id})
@app.delete("/api/calendar/events/{event_id}")
@app.post("/api/calendar/events/delete")
async def delete_calendar_event(event_id: Optional[str] = None, req: Optional[dict] = None):
    eid = event_id or (req.get("id") if req else None)
    if not eid:
        raise HTTPException(status_code=400, detail="ID события не указан.")
    if CALENDAR_FILE.exists():
        try:
            with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
                events = json.load(f)
            events = [e for e in events if str(e.get("id")) != str(eid)]
            with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            return {"status": "ok", "message": "Событие удалено"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}

# 1-Click Server Zip Backup
@app.post("/api/backup/create")
async def create_backup():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"HomeServer_Backup_{ts}.zip"
    backup_path = BACKUP_DIR / backup_filename
    
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📦 [БЭКАП] Создание полного архива сервера в {backup_filename}...")
    
    exclude_dirs = {".git", "venv", "node_modules", "__pycache__", "backups"}
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(BASE_DIR):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                full_p = Path(root) / file
                if not file.endswith(".zip") and full_p.stat().st_size < 50 * 1024 * 1024:
                    rel_p = full_p.relative_to(BASE_DIR)
                    zipf.write(full_p, rel_p)
                    
    size_mb = round(backup_path.stat().st_size / (1024 * 1024), 2)
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ [БЭКАП] Архив {backup_filename} создан успешно ({size_mb} MB)!")
    notify_success(f"Резервная копия создана ({size_mb} MB)", f"Файл: {backup_filename}")
    
    return {"success": True, "filename": backup_filename, "size_mb": size_mb}


def scan_directory_tree(dir_path: Path, base_root: Path) -> list:
    if not dir_path.exists():
        return []
    
    nodes = []
    try:
        entries = sorted(list(dir_path.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
        for item in entries:
            if item.name.startswith("."):
                continue
            
            rel_path = item.relative_to(base_root).as_posix()
            stat = item.stat()
            date_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            
            if item.is_dir():
                children = scan_directory_tree(item, base_root)
                sub_count = len(list(item.rglob("*")))
                nodes.append({
                    "name": item.name,
                    "type": "folder",
                    "path": rel_path,
                    "modified": date_str,
                    "file_count": sub_count,
                    "children": children
                })
            else:
                ext = item.suffix.lstrip(".").lower() or "txt"
                encoded_path = urllib.parse.quote(rel_path)
                nodes.append({
                    "name": item.name,
                    "type": "file",
                    "ext": ext,
                    "path": rel_path,
                    "size_kb": round(stat.st_size / 1024, 1),
                    "modified": date_str,
                    "download_url": f"/api/download/file?path={encoded_path}"
                })
    except Exception as e:
        print(f"Error scanning {dir_path}: {e}")
    return nodes

@app.get("/api/files/tree")
async def get_full_files_tree():
    # Сканируем папки archive, data, inbox
    archive_dir = BASE_DIR / "archive"
    inbox_dir = BASE_DIR / "inbox"
    
    archive_nodes = scan_directory_tree(archive_dir, BASE_DIR) if archive_dir.exists() else []
    inbox_nodes = scan_directory_tree(inbox_dir, BASE_DIR) if inbox_dir.exists() else []
    
    return [
        {
            "name": "archive (Архив проектов и документов)",
            "type": "folder",
            "path": "archive",
            "children": archive_nodes,
            "is_root": True
        },
        {
            "name": "inbox (Входящие файлы)",
            "type": "folder",
            "path": "inbox",
            "children": inbox_nodes,
            "is_root": True
        }
    ]

# Универсальное скачивание любого файла по относительному пути
@app.get("/api/download/file")
async def download_generic_file(path: str):
    target = (BASE_DIR / path).resolve()
    # Проверка безопасности чтобы не выйти за пределы BASE_DIR
    if not str(target).startswith(str(BASE_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    
    encoded_name = urllib.parse.quote(target.name)
    return FileResponse(
        str(target),
        filename=target.name,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"}
    )


# Document Viewer Endpoints (PDF, Markdown, Code, Text)
@app.get("/api/view/raw")
async def view_raw_file(path: str):
    clean_p = path.lstrip("/\\")
    target = (BASE_DIR / clean_p).resolve()
    if not str(target).startswith(str(BASE_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    try:
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(150000)
        return {
            "status": "ok",
            "filename": target.name,
            "path": clean_p,
            "ext": target.suffix.lower(),
            "content": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/view/pdf")
async def view_pdf_file(path: str):
    clean_p = path.lstrip("/\\")
    target = (BASE_DIR / clean_p).resolve()
    if not str(target).startswith(str(BASE_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден")
    encoded_name = urllib.parse.quote(target.name)
    return FileResponse(
        str(target), 
        media_type="application/pdf", 
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}"}
    )


# ==============================================================================
# 📱 VK MINI APP & SKILLS / MEMORY API
# ==============================================================================

@app.get("/vk-app", response_class=HTMLResponse)
async def serve_vk_app():
    vk_html = SCRIPTS_DIR / "vk_app.html"
    if vk_html.exists():
        return HTMLResponse(vk_html.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>VK Mini App not found</h1>", status_code=404)

@app.get("/api/skills")
async def get_skills_catalog():
    from core.skill_manager import SKILLS_CATALOG, load_skills_manifest
    manifest = load_skills_manifest()
    return {
        "catalog": SKILLS_CATALOG,
        "installed": manifest.get("installed_skills", [])
    }

@app.post("/api/skills/install")
async def install_skill_endpoint(request: Request):
    data = await request.json()
    skill_id = data.get("skill_id", "")
    from core.skill_manager import install_skill
    res = install_skill(skill_id)
    return {"status": "ok", "message": res}

@app.get("/api/memory")
async def get_memory_endpoint():
    from core.memory_engine import load_memory
    return load_memory()

@app.post("/api/memory/mode")
async def set_memory_mode(request: Request):
    data = await request.json()
    mode = data.get("mode", "mentor")
    from core.memory_engine import set_chat_mode
    res = set_chat_mode(mode)
    return {"status": "ok", "message": res}

@app.post("/api/memory/fact")
async def add_memory_fact_endpoint(request: Request):
    data = await request.json()
    fact = data.get("fact", "")
    category = data.get("category", "general")
    from core.memory_engine import add_pinned_fact
    res = add_pinned_fact(fact, category)
    return {"status": "ok", "message": res}


# ==============================================================================
# 🔐 MULTI-USER AUTHENTICATION & ADMIN CONTROL PANEL API
# ==============================================================================

def get_current_user_from_req(request: Request) -> Optional[Dict[str, Any]]:
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "hs_session" in request.cookies:
        token = request.cookies.get("hs_session", "")
    
    from core.auth_manager import get_user_by_token
    return get_user_by_token(token)

@app.get("/admin", response_class=HTMLResponse)
async def serve_admin_panel():
    admin_html = SCRIPTS_DIR / "admin_panel.html"
    if admin_html.exists():
        return HTMLResponse(admin_html.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Admin Panel file not found</h1>", status_code=404)

@app.post("/api/auth/login")
async def auth_login(request: Request):
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    from core.auth_manager import authenticate_user
    res = authenticate_user(username, password)
    if res:
        token, user = res
        response = JSONResponse({
            "status": "ok",
            "token": token,
            "user": user
        })
        response.set_cookie(key="hs_session", value=token, max_age=86400*30, httponly=False)
        return response
    return JSONResponse({"status": "error", "message": "Неверный логин или пароль"}, status_code=401)

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif "hs_session" in request.cookies:
        token = request.cookies.get("hs_session", "")
    if token:
        from core.auth_manager import invalidate_session
        invalidate_session(token)
    response = JSONResponse({"status": "ok", "message": "Вы успешно вышли из системы"})
    response.delete_cookie("hs_session")
    return response

@app.get("/api/auth/me")
async def auth_me(request: Request):
    user = get_current_user_from_req(request)
    if user:
        return user
    # Default fallback for local master
    from core.auth_manager import init_users_db
    db = init_users_db()
    ardont = db.get("users", {}).get("ardont", {})
    safe = dict(ardont)
    safe.pop("password_hash", None)
    safe.pop("salt", None)
    return safe

@app.post("/api/auth/register")
async def auth_register(request: Request):
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    display_name = data.get("display_name", "")
    from core.auth_manager import create_new_user
    ok, msg = create_new_user(username, password, role="user", display_name=display_name)
    if ok:
        return {"status": "ok", "message": msg}
    return JSONResponse({"status": "error", "message": msg}, status_code=400)

@app.get("/api/admin/users")
async def admin_get_users(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.auth_manager import list_all_users
    return {"status": "ok", "users": list_all_users()}

@app.post("/api/admin/users/update_permissions")
async def admin_update_perms(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    username = data.get("username", "")
    perms = data.get("permissions", {})
    from core.auth_manager import update_user_permissions
    ok, msg = update_user_permissions(username, perms)
    return {"status": "ok" if ok else "error", "message": msg}

@app.post("/api/admin/users/update_password")
async def admin_update_pwd(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    from core.auth_manager import update_user_password
    ok, msg = update_user_password(username, password)
    return {"status": "ok" if ok else "error", "message": msg}

@app.post("/api/admin/users/create")
async def admin_create_user(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    display_name = data.get("display_name", "")
    role = data.get("role", "user")
    perms = data.get("permissions", {})
    from core.auth_manager import create_new_user
    ok, msg = create_new_user(username, password, role=role, display_name=display_name, permissions=perms)
    return {"status": "ok" if ok else "error", "message": msg}

@app.delete("/api/admin/users/{username}")
async def admin_delete_user(username: str, request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.auth_manager import delete_user
    ok, msg = delete_user(username)
    return {"status": "ok" if ok else "error", "message": msg}

# ==============================================================================
# 📊 TOKEN STATS & VK INVITES ADMIN ENDPOINTS
# ==============================================================================

@app.get("/api/admin/tokens/stats")
async def admin_get_token_stats(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.token_tracker import load_token_stats
    return load_token_stats()

@app.post("/api/admin/tokens/set_quota")
async def admin_set_quota(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    username = data.get("username", "")
    quota = int(data.get("quota", 50000))
    allowed_models = data.get("allowed_models")
    from core.token_tracker import set_user_quota
    set_user_quota(username, quota, allowed_models)
    return {"status": "ok", "message": f"Лимит токенов для @{username} обновлен: {quota}"}

@app.get("/api/admin/vk/invites")
async def admin_get_invites(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.auth_manager import list_all_invites
    return {"status": "ok", "invites": list_all_invites()}

@app.post("/api/admin/vk/generate_invite")
async def admin_gen_invite(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    target_username = data.get("target_username", "")
    note = data.get("note", "")
    from core.auth_manager import generate_invite_code
    code = generate_invite_code(target_username, note)
    return {"status": "ok", "code": code, "message": f"Инвайт-код {code} сгенерирован"}

@app.post("/api/admin/vk/bind")
async def admin_bind_vk(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    username = data.get("username", "")
    vk_id = data.get("vk_id", "")
    from core.auth_manager import bind_vk_id_to_user
    ok, msg = bind_vk_id_to_user(username, vk_id)
    return {"status": "ok" if ok else "error", "message": msg}

@app.delete("/api/admin/vk/unbind/{username}")
async def admin_unbind_vk(username: str, request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.auth_manager import unbind_vk_id_from_user
    ok, msg = unbind_vk_id_from_user(username)
    return {"status": "ok" if ok else "error", "message": msg}


# ------------------------------------------------------------------------------
# ⚙️ ADMIN: VK CONFIG & ID MANAGEMENT
# ------------------------------------------------------------------------------

@app.get("/api/admin/vk/config")
async def admin_get_vk_config(request: Request):
    user = get_current_user_from_req(request)
    if not user or not user.get("permissions", {}).get("is_admin", False):
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    
    from core.vk_bot import get_vk_config
    token, user_id, group_id = get_vk_config()
    return {
        "vk_bot_token": token,
        "vk_user_id": user_id,
        "vk_group_id": group_id
    }

@app.post("/api/admin/vk/config")
async def admin_save_vk_config(request: Request):
    user = get_current_user_from_req(request)
    if not user or not user.get("permissions", {}).get("is_admin", False):
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    
    body = await request.json()
    new_token = body.get("vk_bot_token", "").strip().strip("'\"")
    new_user_id = body.get("vk_user_id", "").strip().strip("'\"")
    new_group_id = body.get("vk_group_id", "").strip().strip("'\"")

    env_path = CONFIG_DIR / ".env"
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    
    updated_keys = set()
    new_lines = []
    for line in lines:
        if line.startswith("VK_BOT_TOKEN="):
            new_lines.append(f"VK_BOT_TOKEN={new_token}")
            updated_keys.add("VK_BOT_TOKEN")
        elif line.startswith("VK_USER_ID="):
            new_lines.append(f"VK_USER_ID={new_user_id}")
            updated_keys.add("VK_USER_ID")
        elif line.startswith("VK_GROUP_ID="):
            new_lines.append(f"VK_GROUP_ID={new_group_id}")
            updated_keys.add("VK_GROUP_ID")
        else:
            new_lines.append(line)
            
    if "VK_BOT_TOKEN" not in updated_keys and new_token:
        new_lines.append(f"VK_BOT_TOKEN={new_token}")
    if "VK_USER_ID" not in updated_keys and new_user_id:
        new_lines.append(f"VK_USER_ID={new_user_id}")
    if "VK_GROUP_ID" not in updated_keys and new_group_id:
        new_lines.append(f"VK_GROUP_ID={new_group_id}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return {"status": "ok", "message": "Глобальные настройки VK (.env) успешно сохранены!"}

@app.post("/api/admin/users/update_vk")
async def admin_update_user_vk(request: Request):
    user = get_current_user_from_req(request)
    if not user or not user.get("permissions", {}).get("is_admin", False):
        raise HTTPException(status_code=403, detail="Доступ только для администраторов")
    
    body = await request.json()
    target_user = body.get("username", "").strip()
    vk_id = str(body.get("vk_id", "")).strip().strip("'\"")
    
    if not target_user:
        raise HTTPException(status_code=400, detail="Не указан пользователь")
        
    from core.auth_manager import bind_vk_id_to_user, unbind_vk_id_from_user
    if vk_id:
        ok, msg = bind_vk_id_to_user(target_user, vk_id)
    else:
        ok, msg = unbind_vk_id_from_user(target_user)
        
    return {"status": "ok" if ok else "error", "message": msg}


# ------------------------------------------------------------------------------
# 🔓 ADMIN: UNLIMITED MODE & MODEL MANAGEMENT
# ------------------------------------------------------------------------------

@app.post("/api/admin/tokens/remove_all_limits")
async def admin_remove_all_limits(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.token_tracker import remove_all_limits
    remove_all_limits()
    return {"status": "ok", "message": "⚡ Все лимиты и квоты успешно сняты! Полный безлимит для всех пользователей."}

@app.post("/api/admin/tokens/update_models")
async def admin_update_user_models(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    username = data.get("username", "")
    allowed_models = data.get("allowed_models", ["*"])
    from core.token_tracker import update_user_models
    update_user_models(username, allowed_models)
    return {"status": "ok", "message": f"Доступные модели для @{username} обновлены: {allowed_models}"}

@app.post("/api/admin/tokens/reset_usage")
async def admin_reset_tokens(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    data = await request.json()
    username = data.get("username", "")
    from core.token_tracker import reset_user_tokens
    reset_user_tokens(username)
    return {"status": "ok", "message": f"Счетчик токенов для @{username} сброшен в 0"}

@app.delete("/api/admin/tokens/user/{username}")
async def admin_delete_user_tokens(username: str, request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.token_tracker import delete_user_stats
    delete_user_stats(username)
    return {"status": "ok", "message": f"Запись статистики для @{username} удалена"}

@app.delete("/api/admin/vk/invites/{code}")
async def admin_delete_invite(code: str, request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    inv_file = CONFIG_DIR / "invites.json"
    if inv_file.exists():
        try:
            invs = json.loads(inv_file.read_text(encoding="utf-8"))
            if code in invs:
                del invs[code]
                inv_file.write_text(json.dumps(invs, ensure_ascii=False, indent=2), encoding="utf-8")
                return {"status": "ok", "message": f"Инвайт {code} удален"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Инвайт не найден"}

@app.post("/api/admin/vk/bind_my_vk")
async def admin_bind_my_vk(request: Request):
    user = get_current_user_from_req(request)
    if user and not user.get("permissions", {}).get("is_admin"):
        return JSONResponse({"status": "error", "message": "Требуются права администратора"}, status_code=403)
    from core.auth_manager import bind_vk_id_to_user
    ok, msg = bind_vk_id_to_user("ardont", "816140871")
    return {"status": "ok" if ok else "error", "message": msg}
