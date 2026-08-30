# -*- coding: utf-8 -*-
"""
Dynamic Skills Manager & Auto-Installer for HomeServer AI Hub
Enables the AI Assistant to:
1. Discover & recommend specialized skills (from catalog, GitHub, or local repository).
2. Autonomously install skills (cloning, pip install into venv, dynamic hot-reload of tools).
3. Inject skill-specific prompt instructions (SKILL.md) and tool handlers on the fly.
"""
import os
import sys
import json
import time
import re
import urllib.request
import subprocess
import importlib.util
from pathlib import Path
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = BASE_DIR / "skills"
CONFIG_DIR = BASE_DIR / "config"
MANIFEST_FILE = CONFIG_DIR / "skills_manifest.json"
VENV_PYTHON = BASE_DIR / "venv" / "Scripts" / "python.exe"

SKILLS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# 📚 ОФИЦИАЛЬНЫЙ КАТАЛОГ СКИЛЛОВ (BUILT-IN & GITHUB CATALOG)
# ==============================================================================

SKILLS_CATALOG = [
    {
        "id": "cloud-notebooklm-researcher",
        "name": "📓 Cloud Code & NotebookLM Researcher",
        "description": "Персональный NotebookLM: синтез документов, генерация FAQ, аналитических записок, скриптов подкастов и запуск Cloud Code / Jupyter.",
        "tags": ["notebooklm", "cloud-code", "research", "synthesis", "jupyter", "sources"],
        "packages": ["pandas", "numpy"],
        "system_instruction": "Ты — персональный исследовательский интеллект в стиле Google NotebookLM и Cloud Code. Опирайся на проверенные источники, генерируй глубокие саммари, сценарии подкастов и помогай в анализе кода.",
        "author": "HomeServer Community"
    },
    {
        "id": "web-scraper-automation",
        "name": "🌐 Web Scraper & Marketplace Automation",
        "description": "Продвинутый парсинг интернет-магазинов, каталогов, новостей и маркетплейсов с выгрузкой в CSV/JSON.",
        "tags": ["scraping", "parser", "web", "ecommerce", "data"],
        "packages": ["beautifulsoup4", "lxml"],
        "system_instruction": "Ты — эксперт по парсингу веб-данных. Извлекай чистый структурированный контент (цены, характеристики, таблицы, контакты) и сохраняй в data/.",
        "author": "HomeServer Community"
    },
    {
        "id": "ocr-document-extractor",
        "name": "📄 OCR & Document / Barcode Scanner",
        "description": "Распознавание текста, чеков, накладных, сканов документов и штрихкодов маркировки (Честный Знак, DataMatrix).",
        "tags": ["ocr", "scanner", "barcode", "pdf", "datamatrix", "marking"],
        "packages": ["pillow"],
        "system_instruction": "Ты — специалист по OCR и обработке сканов. Анализируй накладные, вытаскивай реквизиты, суммы, артикулы и коды маркировки DataMatrix.",
        "author": "HomeServer Community"
    },
    {
        "id": "data-science-analyst",
        "name": "📊 Data Science & Machine Learning EDA",
        "description": "Автоматический разведочный анализ данных (EDA), очистка выбросов, корреляции, построение графиков и отчетов.",
        "tags": ["data science", "ml", "pandas", "eda", "shad", "math"],
        "packages": ["pandas", "matplotlib", "seaborn"],
        "system_instruction": "Ты — Senior Data Scientist (уровень ШАД). Анализируй датасеты, генерируй гипотезы, строй графики в archive/plots/ и пиши чистый Python-код.",
        "author": "HomeServer Community"
    },
    {
        "id": "windows-sysadmin-optimizer",
        "name": "💻 Windows 11 SysAdmin & Performance Optimizer",
        "description": "Глубокая диагностика Windows, реестр, оптимизация автозапуска, очистка мусора и управление сетевыми службами.",
        "tags": ["windows", "admin", "ram", "optimizer", "rdp", "powershell"],
        "packages": [],
        "system_instruction": "Ты — эксперт по системному администрированию Windows 11. Находи утечки памяти, оптимизируй службы, настраивай сеть и создавай удобные .bat скрипты.",
        "author": "HomeServer Community"
    },
    {
        "id": "api-bot-integrator",
        "name": "🤖 Multi-Messenger Bot Builder",
        "description": "Генерация, тестирование и интеграция ботов для Telegram, VK, MAX, Discord с поддержкой инлайн-кнопок.",
        "tags": ["bot", "vk", "telegram", "max", "chat", "integration"],
        "packages": ["requests"],
        "system_instruction": "Ты — ведущий разработчик ботов. Проектируй интуитивные клавиатуры, Long Polling обработчики и безопасную передачу файлов.",
        "author": "HomeServer Community"
    },
    {
        "id": "1c-enterprise-integrator",
        "name": "💼 1С:Предприятие & Кассовые Сканеры",
        "description": "Настройка торгового оборудования, драйверов COM-портов, выгрузок XML/DBF и интеграция с Честным Знаком в 1С.",
        "tags": ["1c", "scanner", "com-port", "retail", "marking", "xml"],
        "packages": [],
        "system_instruction": "Ты — эксперт по 1С и торговому оборудованию. Помогай настраивать сканеры, виртуальные COM-порты, суффиксы Enter/GS и форматы обмена XML.",
        "author": "HomeServer Community"
    }
]

def load_skills_manifest() -> Dict[str, Any]:
    if not MANIFEST_FILE.exists():
        initial = {"installed_skills": ["windows-sysadmin-optimizer", "1c-enterprise-integrator"]}
        save_skills_manifest(initial)
        # Create initial skill files
        for s_id in initial["installed_skills"]:
            _create_default_skill_files(s_id)
        return initial
    try:
        with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"installed_skills": []}

def save_skills_manifest(data: Dict[str, Any]) -> None:
    try:
        with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Skills Manifest Error]: {e}")

def _create_default_skill_files(skill_id: str) -> None:
    s_meta = next((s for s in SKILLS_CATALOG if s["id"] == skill_id), None)
    if not s_meta:
        return
    s_dir = SKILLS_DIR / skill_id
    s_dir.mkdir(parents=True, exist_ok=True)
    
    skill_md = s_dir / "SKILL.md"
    if not skill_md.exists():
        content = f"""# {s_meta['name']}

**ID:** {s_meta['id']}
**Автор:** {s_meta.get('author', 'HomeServer')}
**Описание:** {s_meta['description']}

## Инструкции и Правила:
{s_meta['system_instruction']}
"""
        with open(skill_md, "w", encoding="utf-8") as f:
            f.write(content)

def list_installed_skills() -> List[Dict[str, Any]]:
    manifest = load_skills_manifest()
    installed_ids = manifest.get("installed_skills", [])
    res = []
    for s_id in installed_ids:
        s_meta = next((s for s in SKILLS_CATALOG if s["id"] == s_id), {"id": s_id, "name": s_id, "description": "Пользовательский навык"})
        res.append(s_meta)
    return res

def search_skills(query: str) -> List[Dict[str, Any]]:
    """Ищет скиллы в каталоге по ключевым словам запроса."""
    q_words = set(re.findall(r'\w+', query.lower()))
    matches = []
    for s in SKILLS_CATALOG:
        s_text = f"{s['id']} {s['name']} {s['description']} {' '.join(s.get('tags', []))}".lower()
        score = sum(1 for w in q_words if w in s_text)
        if score > 0:
            matches.append((score, s))
    matches.sort(key=lambda x: x[0], reverse=True)
    return [m[1] for m in matches]

def recommend_skills_for_task(task_text: str) -> Optional[str]:
    """Анализирует задачу пользователя и формирует ненавязчивую подсказку по скиллам."""
    matches = search_skills(task_text)
    manifest = load_skills_manifest()
    installed = set(manifest.get("installed_skills", []))
    
    uninstalled = [s for s in matches if s["id"] not in installed]
    if uninstalled:
        top_skill = uninstalled[0]
        return f"💡 Для этой задачи доступен навык **«{top_skill['name']}»**.\n{top_skill['description']}\nЧтобы установить, напишите: `установи скилл {top_skill['id']}`."
    return None

def install_skill(skill_id_or_url: str) -> str:
    """Автономно устанавливает скилл: скачивает/создает файлы, ставит pip-пакеты, регистрирует в манифесте."""
    clean_id = skill_id_or_url.strip().lower()
    
    # 1. Check if git repo URL
    if clean_id.startswith("http://") or clean_id.startswith("https://"):
        repo_name = clean_id.rstrip("/").split("/")[-1].replace(".git", "")
        dest_dir = SKILLS_DIR / repo_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Git clone / download
        from core.agent_tools import tool_git_clone
        tool_git_clone(clean_id, str(dest_dir))
        
        manifest = load_skills_manifest()
        if repo_name not in manifest.get("installed_skills", []):
            manifest.setdefault("installed_skills", []).append(repo_name)
            save_skills_manifest(manifest)
        return f"✅ Навык из репозитория '{repo_name}' успешно установлен в skills/{repo_name}!"

    # 2. Check catalog
    s_meta = next((s for s in SKILLS_CATALOG if s["id"] == clean_id or clean_id in s["id"]), None)
    if not s_meta:
        return f"❌ Скилл '{skill_id_or_url}' не найден в каталоге. Напишите `каталог скиллов` чтобы увидеть список."

    skill_id = s_meta["id"]
    _create_default_skill_files(skill_id)

    # 3. Install packages if required
    packages = s_meta.get("packages", [])
    if packages and VENV_PYTHON.exists():
        try:
            print(f"📦 [Skills Auto-Installer] Установка пакетов для {skill_id}: {packages}")
            subprocess.run(
                [str(VENV_PYTHON), "-m", "pip", "install", *packages],
                capture_output=True,
                text=True,
                timeout=90
            )
        except Exception as e:
            print(f"[Skills pip error]: {e}")

    manifest = load_skills_manifest()
    if skill_id not in manifest.get("installed_skills", []):
        manifest.setdefault("installed_skills", []).append(skill_id)
        save_skills_manifest(manifest)

    return f"🚀 Навык **«{s_meta['name']}»** успешно установлен и активирован!\n{s_meta['description']}"

def get_installed_skills_prompt_instructions() -> str:
    """Собирает системные инструкции из всех активных SKILL.md."""
    manifest = load_skills_manifest()
    installed = manifest.get("installed_skills", [])
    prompts = []
    for s_id in installed:
        sk_file = SKILLS_DIR / s_id / "SKILL.md"
        if sk_file.exists():
            try:
                with open(sk_file, "r", encoding="utf-8") as f:
                    prompts.append(f"--- НАВЫК: {s_id} ---\n" + f.read()[:1000])
            except Exception:
                pass
    return "\n\n".join(prompts)
