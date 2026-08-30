# -*- coding: utf-8 -*-
"""
AI File Organizer Module for HomeServer
Monitors INBOX folders, anonymizes sensitive PII data locally via Privacy Shield,
analyzes files & images/screenshots with Google Gemini 3.6 Flash using User Profile Context,
and prepares organization proposals with manual approval, deletion, and rollback support.
"""
import os
import sys
import time
import json
import shutil
import datetime
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.notifier import notify_info, notify_warning, notify_error, log_event
from core.privacy_shield import sanitize_text

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / ".env"
PROFILE_PATH = BASE_DIR / "config" / "user_profile.json"

if CONFIG_PATH.exists():
    load_dotenv(CONFIG_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
INBOX_DIRS = [
    BASE_DIR / "inbox",
    Path(os.path.expanduser("~/Desktop/INBOX_СЕРВЕР"))
]
DATA_DIR = BASE_DIR / "data"
PROCESSED_DIR = BASE_DIR / "processed"
PROPOSALS_FILE = BASE_DIR / "inbox_proposals.json"

CATEGORIES = {
    "documents": [".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".epub", ".djvu"],
    "spreadsheets": [".xlsx", ".xls", ".csv", ".tsv", ".ods"],
    "code": [".py", ".js", ".ts", ".html", ".css", ".json", ".sql", ".sh", ".bat", ".ps1", ".cpp", ".java", ".ipynb"],
    "media": [".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".mp4", ".mov", ".mp3", ".wav"],
    "archives": [".zip", ".tar", ".gz", ".7z", ".rar", ".apk"]
}

def get_user_profile_context() -> str:
    if not PROFILE_PATH.exists():
        return ""
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            prof = json.load(f)
            return (
                f"КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:\n"
                f"- Имя: {prof.get('user_name', 'Пользователь')}\n"
                f"- О себе / интересы: {prof.get('bio', '')}\n"
                f"- Активные проекты: {json.dumps(prof.get('active_projects', []), ensure_ascii=False)}\n"
                f"- Правила сортировки: {prof.get('sorting_rules', '')}\n"
            )
    except Exception:
        return ""

def extract_file_sample(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext in [".txt", ".md", ".py", ".js", ".ts", ".html", ".css", ".json", ".csv", ".sql", ".sh", ".bat", ".ps1"]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(3000)
        except Exception:
            return ""
            
    if ext == ".pdf":
        try:
            with open(file_path, "rb") as f:
                raw = f.read(4000)
                decoded = raw.decode("utf-8", errors="ignore")
                cleaned = "".join([c for c in decoded if c.isalnum() or c.isspace()])
                return cleaned[:1000] if len(cleaned) > 20 else f"PDF Document: {file_path.name}"
        except Exception:
            return f"PDF Document: {file_path.name}"
            
    return f"File: {file_path.name} (Type: {ext})"

def analyze_with_gemini(file_path: Path) -> dict:
    ext = file_path.suffix.lower()
    category = "documents"
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            category = cat
            break
            
    user_context = get_user_profile_context()
    
    if not GEMINI_API_KEY:
        return {
            "summary": f"Файл {file_path.name}",
            "category": category,
            "suggested_subfolder": "general",
            "tags": [category, ext.replace(".", "")],
            "analyzed_by": "Rule-based (No API Key)"
        }
        
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        is_image = ext in [".png", ".jpg", ".jpeg", ".webp"]
        
        system_instruction = (
            "Ты — умный AI-ассистент домашнего сервера. Проанализируй входящий файл (или скриншот) и определи, "
            "в какую папку его лучше всего положить, учитывая профиль и активные проекты пользователя.\n\n"
            + user_context + "\n\n"
            + "ОСНОВНЫЕ КАТЕГОРИИ (category):\n"
            + "- documents (документы, PDF, книги, статьи, учеба, лекции, ШАД)\n"
            + "- spreadsheets (таблицы, финансы, отчеты, CSV, Excel)\n"
            + "- code (исходный код, скрипты, проекты, репозитории)\n"
            + "- media (скриншоты, картинки, видео, фотографии)\n"
            + "- archives (архивы, бекапы, APK)\n\n"
            + "ВЕРНИ ОТВЕТ СТРОГО В ВИДЕ JSON:\n"
            + "{\n"
            + '  "category": "одна из 5 категорий",\n'
            + '  "suggested_subfolder": "относительный путь внутри data/category, например: education/shad или screenshots или python",\n'
            + '  "summary": "Краткое описание файла или скриншота на русском языке (1-2 предложения)",\n'
            + '  "tags": ["тег1", "тег2"]\n'
            + "}"
        )
        
        if is_image:
            mime = "image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else "image/jpeg")
            with open(file_path, "rb") as f:
                img_bytes = f.read()
            contents = [
                types.Part.from_bytes(data=img_bytes, mime_type=mime),
                system_instruction + f"\nИмя файла скриншота: {file_path.name}"
            ]
        else:
            raw_sample = extract_file_sample(file_path)
            safe_sample, _ = sanitize_text(raw_sample)
            contents = system_instruction + f"\n\nФАЙЛ: {file_path.name}\nСодержимое:\n{safe_sample[:2000]}"
            
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents
        )
        
        resp_text = response.text.strip()
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()
            
        data = json.loads(resp_text)
        return {
            "summary": data.get("summary", f"Файл {file_path.name}"),
            "category": data.get("category", category),
            "suggested_subfolder": data.get("suggested_subfolder", "general").strip("/\\"),
            "tags": data.get("tags", [category]),
            "analyzed_by": "Google Gemini 3.6 Flash (Multimodal)"
        }
    except Exception as e:
        print(f"Gemini API Error for {file_path.name}: {e}")
        return {
            "summary": f"Файл {file_path.name}",
            "category": category,
            "suggested_subfolder": "general",
            "tags": [category],
            "analyzed_by": "Rule-based"
        }

def scan_and_process_inbox(auto_apply: bool = False) -> int:
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing_proposals = []
    if PROPOSALS_FILE.exists():
        try:
            with open(PROPOSALS_FILE, "r", encoding="utf-8") as f:
                existing_proposals = json.load(f)
        except Exception:
            existing_proposals = []
            
    processed_paths = {p.get("original_path") for p in existing_proposals}
    new_proposals_count = 0
    
    for inbox_dir in INBOX_DIRS:
        if not inbox_dir.exists():
            continue
            
        for file_path in inbox_dir.glob("*"):
            if not file_path.is_file():
                continue
            if file_path.name.startswith((".", "~$", "desktop.ini")):
                continue
            if str(file_path) in processed_paths:
                continue
                
            print(f"🔍 Обнаружен новый файл: {file_path.name}")
            ai_meta = analyze_with_gemini(file_path)
            
            category = ai_meta.get("category", "documents")
            subfolder = ai_meta.get("suggested_subfolder", "general")
            dest_dir = DATA_DIR / category / subfolder
            target_dest_file = dest_dir / file_path.name
            
            proposal_id = f"prop_{int(time.time())}_{abs(hash(file_path.name)) % 10000}"
            size_kb = round(file_path.stat().st_size / 1024, 1)
            
            proposal = {
                "id": proposal_id,
                "file_name": file_path.name,
                "original_path": str(file_path),
                "file_size_kb": size_kb,
                "detected_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "pending",
                "summary": ai_meta.get("summary", ""),
                "category": category,
                "suggested_destination": str(target_dest_file),
                "actual_destination": None,
                "tags": ai_meta.get("tags", []),
                "analyzed_by": ai_meta.get("analyzed_by", "")
            }
            
            existing_proposals.append(proposal)
            processed_paths.add(str(file_path))
            new_proposals_count += 1
            
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_proposals, f, ensure_ascii=False, indent=2)
        
    return new_proposals_count

def apply_proposal(proposal_id: str, new_destination: str = None) -> bool:
    if not PROPOSALS_FILE.exists(): return False
    with open(PROPOSALS_FILE, "r", encoding="utf-8") as f:
        proposals = json.load(f)
        
    target_prop = next((p for p in proposals if p["id"] == proposal_id), None)
    if not target_prop: return False
        
    src = Path(target_prop["original_path"])
    if not src.exists():
        target_prop["status"] = "error"
        target_prop["error"] = "Исходный файл не найден"
        with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
            json.dump(proposals, f, ensure_ascii=False, indent=2)
        return False
        
    dest_str = new_destination if new_destination else target_prop["suggested_destination"]
    dest = Path(dest_str)
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    if dest.exists() and dest != src:
        stem, ext = dest.stem, dest.suffix
        dest = dest.parent / f"{stem}_{int(time.time())}{ext}"
        
    shutil.move(str(src), str(dest))
    target_prop["status"] = "moved"
    target_prop["actual_destination"] = str(dest)
    target_prop["applied_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        json.dump(proposals, f, ensure_ascii=False, indent=2)
    return True

def delete_proposal(proposal_id: str, delete_physical_file: bool = True) -> bool:
    if not PROPOSALS_FILE.exists(): return False
    with open(PROPOSALS_FILE, "r", encoding="utf-8") as f:
        proposals = json.load(f)
        
    target_prop = next((p for p in proposals if p["id"] == proposal_id), None)
    if not target_prop: return False
        
    if delete_physical_file:
        try:
            target_path = Path(target_prop.get("actual_destination") or target_prop.get("original_path"))
            if target_path.exists() and target_path.is_file():
                target_path.unlink()
        except Exception as e:
            print(f"Error deleting file: {e}")
            
    proposals = [p for p in proposals if p["id"] != proposal_id]
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        json.dump(proposals, f, ensure_ascii=False, indent=2)
    return True

def revert_proposal(proposal_id: str) -> bool:
    if not PROPOSALS_FILE.exists(): return False
    with open(PROPOSALS_FILE, "r", encoding="utf-8") as f:
        proposals = json.load(f)
        
    target_prop = next((p for p in proposals if p["id"] == proposal_id), None)
    if not target_prop: return False
        
    act_dest = target_prop.get("actual_destination")
    if not act_dest: return False
    
    cur_file = Path(act_dest)
    if not cur_file.exists(): return False
        
    orig = Path(target_prop["original_path"])
    orig.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(cur_file), str(orig))
    
    target_prop["status"] = "pending"
    target_prop["actual_destination"] = None
    
    with open(PROPOSALS_FILE, "w", encoding="utf-8") as f:
        json.dump(proposals, f, ensure_ascii=False, indent=2)
    return True
