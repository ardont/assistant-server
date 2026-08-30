# -*- coding: utf-8 -*-
"""
Folder & Git Repository Smart Processor with Custom AI Instructions for HomeServer.
Allows processing entire multi-file project folders or Git repos with explicit user comments/instructions.
"""
import os
import sys
import json
import shutil
import subprocess
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
INBOX_DIR = BASE_DIR / "inbox"
ARCHIVE_DIR = BASE_DIR / "archive"
CONFIG_PATH = BASE_DIR / "config" / ".env"
PROFILE_PATH = BASE_DIR / "config" / "user_profile.json"
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.append(str(SCRIPTS_DIR))

if CONFIG_PATH.exists():
    load_dotenv(CONFIG_PATH, override=True)

from core.notifier import notify_info
from core.privacy_shield import sanitize_text

def _get_gemini_keys() -> List[str]:
    k1 = os.getenv("GEMINI_API_KEY", "")
    k2 = os.getenv("GEMINI_BACKUP_KEY", "")
    return [k for k in [k1, k2] if k]

def _read_folder_overview(folder_path: Path, max_files: int = 30) -> Dict[str, Any]:
    """Считывает структуру папки, список файлов и ключевые фрагменты кода/текста."""
    file_list = []
    text_snippets = []
    
    instruction_content = ""
    instruction_names = ["instruction.txt", "инструкция.txt", "readme.txt", "note.txt", "prompt.txt", "comment.txt", "комментарий.txt", "что_сделать.txt"]
    
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in [".git", "node_modules", "venv", "__pycache__", ".idea", ".vscode"]]
        for f in files:
            full_p = Path(root) / f
            rel_p = full_p.relative_to(folder_path)
            file_list.append(str(rel_p))
            
            # Проверяем файл инструкции
            if f.lower() in instruction_names and not instruction_content:
                try:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as inst_f:
                        instruction_content = inst_f.read().strip()
                except Exception:
                    pass

            # Считываем содержимое ключевых файлов
            ext = full_p.suffix.lower()
            if len(text_snippets) < max_files and ext in [".md", ".py", ".txt", ".json", ".yaml", ".yml", ".ipynb", ".sh", ".sql"]:
                try:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as text_f:
                        head = text_f.read(1500)
                        text_snippets.append(f"--- Файл: {rel_p} ---\n{head}")
                except Exception:
                    pass

    return {
        "folder_name": folder_path.name,
        "total_files": len(file_list),
        "files_sample": file_list[:40],
        "instruction_found": instruction_content,
        "snippets": "\n\n".join(text_snippets[:15])
    }

def process_folder_with_ai(folder_path: Path, user_comment: str = "") -> Dict[str, Any]:
    """
    Анализирует всю папку/репозиторий целиком с учётом комментария пользователя.
    Определяет категорию, выполняет инструкцию, извлекает задачи и сохраняет в архив.
    """
    if not folder_path.exists() or not folder_path.is_dir():
        return {"success": False, "error": f"Папка {folder_path} не найдена."}

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📁 [ПАПКА] Начало обработки папки '{folder_path.name}'...")
    overview = _read_folder_overview(folder_path)
    
    final_instruction = user_comment.strip() or overview.get("instruction_found", "") or "Проанализируй проект, категоризируй и выдели пользу."
    
    # Считываем профиль пользователя
    user_context = "Подготовка в ШАД, Data Science, Python, крипто-проекты."
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                p = json.load(f)
                user_context = f"{p.get('bio', '')}, проекты: {p.get('active_projects', [])}"
        except Exception:
            pass

    prompt = f"""
Ты — персональный ИИ-ассистент HomeServer. Пользователь передал целую папку / проект на обработку.

НАЗВАНИЕ ПАПКИ: {overview['folder_name']}
ВСЕГО ФАЙЛОВ: {overview['total_files']}
СПИСОК ФАЙЛОВ: {json.dumps(overview['files_sample'], ensure_ascii=False)}

ФРАГМЕНТЫ КОДА И МАТЕРИАЛОВ:
{overview['snippets']}

ИНСТРУКЦИЯ И КОММЕНТАРИЙ ОТ ПОЛЬЗОВАТЕЛЯ (ЧТО НУЖНО СДЕЛАТЬ С ПАПКОЙ):
"{final_instruction}"

КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
{user_context}

ТВОЯ ЗАДАЧА:
1. Выполнить указание пользователя.
2. Определить целевую категорию для архива: "education" (ШАД, лекции, математика), "active_projects" (код, скрипты, боты), "finances" (крипта, отчёты), "books", или "general".
3. Сформировать понятное резюме проекта и список ключевых выводов или шагов.

Сформируй ответ СТРОГО в виде JSON без лишнего текста и без кавычек ```json:
{{
  "project_title": "Понятное красивое название проекта/папки",
  "category": "education/active_projects/finances/books/general",
  "summary": "Краткое описание проекта (2-3 предложения) с ответом на инструкцию пользователя.",
  "key_findings": [
    "Ключевой пункт 1",
    "Ключевой пункт 2",
    "Ключевой пункт 3"
  ],
  "action_applied": "Что конкретно сделано в соответствии с инструкцией пользователя",
  "suggested_next_steps": "Что рекомендуется сделать дальше с этими материалами"
}}
"""
    keys = _get_gemini_keys()
    result_data = None

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
            result_data = json.loads(raw)
            break
        except Exception as e:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [!] Ошибка ИИ для папки ({k[:8]}...): {e}")

    # Локальный фоллбэк если ИИ недоступен
    if not result_data:
        cat = "active_projects" if any(f.endswith(".py") for f in overview["files_sample"]) else "education"
        result_data = {
            "project_title": overview["folder_name"].replace("_", " ").title(),
            "category": cat,
            "summary": f"Папка содержит {overview['total_files']} файлов. Обработана по инструкции: '{final_instruction}'.",
            "key_findings": [f"Файлов в структуре: {overview['total_files']}", "Проект сохранён и доступен в архиве."],
            "action_applied": f"Применена инструкция: {final_instruction}",
            "suggested_next_steps": "Изучить исходный код и запустить ключевые модули."
        }

    # Перемещаем папку в соответствующую категорию архива
    target_category = result_data.get("category", "general")
    target_dir = ARCHIVE_DIR / target_category / overview["folder_name"]
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    shutil.move(str(folder_path), str(target_dir))
    
    # Сохраняем карточку анализа AI_PROJECT_SUMMARY.md внутри папки
    card_path = target_dir / "AI_PROJECT_SUMMARY.md"
    summary_md = f"""# 📦 {result_data.get('project_title')}
**Дата обработки:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}  
**Категория:** `{target_category}`  
**Инструкция пользователя:** *«{final_instruction}»*

---

## 📝 Описание и Анализ
{result_data.get('summary')}

## 🔑 Ключевые моменты
""" + "\n".join([f"- {item}" for item in result_data.get("key_findings", [])]) + f"""

## ⚡ Выполненное действие
{result_data.get('action_applied')}

## 💡 Рекомендуемые следующие шаги
{result_data.get('suggested_next_steps')}
"""
    try:
        with open(card_path, "w", encoding="utf-8") as f:
            f.write(summary_md)
    except Exception:
        pass

    # Если это активный проект — обновляем память профиля
    if target_category == "active_projects" and PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                prof = json.load(f)
            projs = prof.get("active_projects", [])
            if overview["folder_name"] not in projs:
                projs.append(overview["folder_name"])
                prof["active_projects"] = projs
                with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                    json.dump(prof, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # Отправляем пуш-уведомление на телефон
    push_title = f"📁 Проект обработан: {result_data.get('project_title')}"
    push_body = f"Категория: {target_category}\n{result_data.get('summary')}"
    notify_info(push_title, push_body)

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ [ПАПКА] Папка '{overview['folder_name']}' успешно перемещена в {target_dir}!")
    
    return {
        "success": True,
        "project_title": result_data.get("project_title"),
        "category": target_category,
        "target_path": str(target_dir),
        "summary": result_data.get("summary"),
        "action_applied": result_data.get("action_applied")
    }

def clone_and_process_git_repo(repo_url: str, user_comment: str = "") -> Dict[str, Any]:
    """
    Клонирует Git репозиторий в INBOX и запускает полную AI обработку по инструкции.
    """
    repo_url = repo_url.strip()
    if not repo_url.startswith("http://") and not repo_url.startswith("https://") and not repo_url.startswith("git@"):
        return {"success": False, "error": "Некорректный URL репозитория."}

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    temp_target = INBOX_DIR / repo_name
    
    if temp_target.exists():
        shutil.rmtree(temp_target, ignore_errors=True)

    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🐙 [GIT] Клонирование репозитория {repo_url} в INBOX...")
    try:
        res = subprocess.run(["git", "clone", "--depth", "1", repo_url, str(temp_target)], capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            return {"success": False, "error": f"Ошибка git clone: {res.stderr}"}
    except Exception as e:
        return {"success": False, "error": f"Не удалось выполнить git clone: {e}"}

    return process_folder_with_ai(temp_target, user_comment)
