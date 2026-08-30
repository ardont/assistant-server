# -*- coding: utf-8 -*-
"""
Smart AI File & Folder Organizer for HomeServer (Non-blocking & Key Rotating).
Scans C:/HomeServer/inbox for both individual files AND full project folders.
"""
import os
import sys
import json
import time
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
INBOX_DIR = BASE_DIR / "inbox"
ARCHIVE_DIR = BASE_DIR / "archive"
LOG_DIR = BASE_DIR / "logs"
CONFIG_PATH = BASE_DIR / "config" / ".env"
CALENDAR_FILE = BASE_DIR / "calendar_events.json"
PROFILE_PATH = BASE_DIR / "config" / "user_profile.json"
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.append(str(SCRIPTS_DIR))

if CONFIG_PATH.exists():
    load_dotenv(CONFIG_PATH, override=True)

from core.privacy_shield import sanitize_text
from core.notifier import notify_success, notify_calendar_event
from core.folder_processor import process_folder_with_ai

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt", ".md", ".py", ".ipynb",
    ".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".zip", ".json"
}

def get_keys():
    k1 = os.getenv("GEMINI_API_KEY", "")
    k2 = os.getenv("GEMINI_BACKUP_KEY", "")
    return [k for k in [k1, k2] if k]

def extract_text_snippet(file_path: Path, max_chars: int = 4000) -> str:
    ext = file_path.suffix.lower()
    text = ""
    try:
        if ext in [".txt", ".md", ".py", ".json", ".csv"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(max_chars)
        elif ext == ".pdf":
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            for page in reader.pages[:4]:
                t = page.extract_text()
                if t:
                    text += t + "\n"
                if len(text) >= max_chars:
                    break
        elif ext in [".docx", ".doc"]:
            import docx
            doc = docx.Document(str(file_path))
            for p in doc.paragraphs[:25]:
                text += p.text + "\n"
        elif ext == ".ipynb":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                nb = json.load(f)
                for cell in nb.get("cells", [])[:10]:
                    if cell.get("cell_type") in ["markdown", "code"]:
                        src = "".join(cell.get("source", []))
                        text += src + "\n"
    except Exception as e:
        text = f"Ошибка извлечения текста: {e}"
    return text[:max_chars]

def analyze_file_with_ai(file_path: Path) -> Dict[str, Any]:
    raw_text = extract_text_snippet(file_path)
    clean_text, scrub_log = sanitize_text(raw_text)

    prompt = f"""
Ты — персональный умный сортировщик файлов HomeServer.
Проанализируй документ и категоризируй его.

ИМЯ ФАЙЛА: {file_path.name}
СОДЕРЖИМОЕ (фрагмент):
{clean_text}

Категории:
- "education": Учеба, ШАД, высшая математика, лекции, конспекты, формулы.
- "active_projects": Проекты по коду, боты, скрипты, разработка.
- "finances": Финансы, крипта, отчеты, выписки.
- "books": Книги, учебники, справочники.
- "general": Прочие документы.

Формат JSON:
{{
  "category": "education/active_projects/finances/books/general",
  "summary": "Краткое резюме файла на 1-2 предложения",
  "suggested_filename": "понятное_имя{file_path.suffix.lower()}",
  "deadlines_or_events": [
    {{"title": "Название события/дедлайна", "date": "YYYY-MM-DD", "details": "детали"}}
  ]
}}
"""
    keys = get_keys()
    for k in keys:
        try:
            from google import genai
            client = genai.Client(api_key=k)
            resp = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            raw = resp.text.strip()
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            return json.loads(raw)
        except Exception:
            pass

    # Локальный фоллбэк
    ext = file_path.suffix.lower()
    cat = "education" if ext == ".pdf" else ("active_projects" if ext in [".py", ".ipynb"] else "general")
    return {
        "category": cat,
        "summary": f"Файл {file_path.name} сохранён в категорию {cat}.",
        "suggested_filename": file_path.name,
        "deadlines_or_events": []
    }

def scan_and_organize_inbox() -> int:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Сначала проверяем вложенные папки в INBOX
    entries = list(INBOX_DIR.iterdir())
    processed_count = 0

    for item in entries:
        if item.is_dir() and item.name not in [".git", "node_modules", "temp"]:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📁 [INBOX] Обнаружена папка: '{item.name}'. Запуск анализа проекта...")
            res = process_folder_with_ai(item)
            if res.get("success"):
                processed_count += 1
        elif item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📄 [INBOX] Анализ файла: '{item.name}'...")
            analysis = analyze_file_with_ai(item)
            cat = analysis.get("category", "general")
            target_folder = ARCHIVE_DIR / cat
            target_folder.mkdir(parents=True, exist_ok=True)
            
            dest = target_folder / item.name
            if dest.exists():
                dest = target_folder / f"{item.stem}_{int(time.time())}{item.suffix}"
            shutil.move(str(item), str(dest))
            
            # Сохраняем дедлайны
            for ev in analysis.get("deadlines_or_events", []):
                try:
                    events = []
                    if CALENDAR_FILE.exists():
                        with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
                            events = json.load(f)
                    events.append({
                        "id": f"evt_{int(time.time())}",
                        "title": ev.get("title", "Дедлайн"),
                        "date": ev.get("date", datetime.date.today().strftime("%Y-%m-%d")),
                        "description": ev.get("details", ""),
                        "category": cat,
                        "source": item.name
                    })
                    with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
                        json.dump(events, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            notify_success(f"Файл обработан: {item.name}", f"Категория: {cat}\n{analysis.get('summary')}")
            processed_count += 1

    return processed_count

if __name__ == "__main__":
    count = scan_and_organize_inbox()
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [✓] Обработано объектов в INBOX: {count}")
