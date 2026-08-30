# -*- coding: utf-8 -*-
"""
Multi-Track Growth & Study Engine for HomeServer AI Hub (HomeServer)
Manages user development tracks (ШАД, Data Science, Python, Projects),
milestones, study materials, and intermediate progress check-ins.
"""
import os
import sys
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
DOCS_DIR = BASE_DIR / "documents"
STUDY_GUIDES_DIR = DOCS_DIR / "study_guides"
TRACKS_FILE = CONFIG_DIR / "user_tracks.json"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)
STUDY_GUIDES_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TRACKS = {
    "ardont": {
        "tracks": [
            {
                "id": "shad_math",
                "title": "🎓 Поступление в ШАД (Яндекс) & Математика ML",
                "category": "Education",
                "status": "in_progress",
                "progress_percent": 35,
                "target_date": "2026-05-01",
                "focus_area": "Линейная алгебра (SVD, спектральное разложение) & Теория вероятностей",
                "topics": [
                    {"name": "Линейная алгебра: Собственные значения и квадратичные формы", "completed": True, "notes": "Разобраны базовые теоремы и положительная определенность"},
                    {"name": "Сингулярное разложение (SVD) и псевдообратные матрицы", "completed": False, "notes": "Требуется решение практических задач из вступительных ШАД"},
                    {"name": "Многомерный матанализ: Градиенты, матрицы Гессе и оптимизация", "completed": False, "notes": "Запланировано на следующую неделю"},
                    {"name": "Теория вероятностей: Случайные величины, неравенства Чебышева и ЦПТ", "completed": False, "notes": "В процессе подготовки"},
                    {"name": "Алгоритмы и структуры данных: Графы, ДП и деревья отрезков", "completed": False, "notes": "Практика на LeetCode / Codeforces"}
                ],
                "recent_notes": "Разобраны основы положительной определенности матриц. Нужно составить Study Guide по SVD-разложению."
            },
            {
                "id": "homeserver_dev",
                "title": "⚡ HomeServer AI Hub & Автоматизация Workspace",
                "category": "Development",
                "status": "in_progress",
                "progress_percent": 80,
                "target_date": "2026-03-15",
                "focus_area": "Интеграция OmniRoute, VK Bot 24/7, NotebookLM и Antigravity UI",
                "topics": [
                    {"name": "Мульти-мессенджер ядро (VK LongPoll & Telegram)", "completed": True, "notes": "VK Bot активен, токен и привязка к ardont настроены"},
                    {"name": "Google NotebookLM & Study Guide синтезатор", "completed": True, "notes": "Интегрирован в agent_tools"},
                    {"name": "Веб-интерфейс в стиле Antigravity IDE", "completed": False, "notes": "В процессе финальной сборки"},
                    {"name": "Сетевая папка INBOX и транскрибатор аудио", "completed": True, "notes": "Работает"}
                ],
                "recent_notes": "VK Bot успешно настроен. Переходим к интеграции шлюза OmniRoute и обновлению дашборда."
            },
            {
                "id": "crypto_web3",
                "title": "📈 Data Science & Аналитика в Web3 / Проектах",
                "category": "Projects",
                "status": "planned",
                "progress_percent": 15,
                "target_date": "2026-06-01",
                "focus_area": "Парсинг ончейн данных, анализ метрик и автоматические стратегии",
                "topics": [
                    {"name": "Сбор и очистка исторических данных", "completed": True, "notes": "Скрипты сбора написаны"},
                    {"name": "Бэктестинг статистических моделей на Python", "completed": False, "notes": "В планах"}
                ],
                "recent_notes": "Базовые скрипты подготовлены."
            }
        ],
        "daily_focus": "Сингулярное разложение (SVD) для ШАД + Запуск Antigravity дашборда",
        "last_checkin": time.strftime("%Y-%m-%d %H:%M:%S")
    }
}

def load_user_tracks(username: str = "ardont") -> Dict[str, Any]:
    clean_user = (username or "ardont").strip().lower()
    if not TRACKS_FILE.exists():
        save_all_tracks(DEFAULT_TRACKS)
        return DEFAULT_TRACKS.get(clean_user, {"tracks": []})
    try:
        with open(TRACKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if clean_user not in data:
                data[clean_user] = DEFAULT_TRACKS.get(clean_user, {"tracks": []})
                save_all_tracks(data)
            return data.get(clean_user, {"tracks": []})
    except Exception as e:
        print(f"[Growth Tracker] Ошибка чтения user_tracks.json: {e}")
        return DEFAULT_TRACKS.get(clean_user, {"tracks": []})

def save_all_tracks(data: Dict[str, Any]) -> bool:
    try:
        with open(TRACKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Growth Tracker] Ошибка сохранения user_tracks.json: {e}")
        return False

def get_tracks_summary_for_prompt(username: str = "ardont") -> str:
    """Генерирует компактную текстовую выжимку треков для системного промпта LLM."""
    u_data = load_user_tracks(username)
    tracks = u_data.get("tracks", [])
    if not tracks:
        return "Нет активных треков развития."
        
    lines = [f"ТЕКУЩИЕ НАПРАВЛЕНИЯ РАЗВИТИЯ @{username}:"]
    for t in tracks:
        status_icon = "🔥" if t.get("status") == "in_progress" else "📌"
        lines.append(f"{status_icon} [{t.get('title')}] — Прогресс: {t.get('progress_percent', 0)}%")
        lines.append(f"   Фокус: {t.get('focus_area')}")
        uncompleted = [top.get('name') for top in t.get('topics', []) if not top.get('completed')]
        if uncompleted:
            lines.append(f"   Ближайшие темы: {', '.join(uncompleted[:2])}")
    
    if u_data.get("daily_focus"):
        lines.append(f"🎯 Главный фокус на сегодня: {u_data.get('daily_focus')}")
        
    return "\n".join(lines)

def update_daily_focus(username: str, focus_text: str) -> bool:
    all_data = {}
    if TRACKS_FILE.exists():
        try:
            with open(TRACKS_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            pass
    clean_user = (username or "ardont").strip().lower()
    u_data = all_data.setdefault(clean_user, {"tracks": []})
    u_data["daily_focus"] = focus_text
    u_data["last_checkin"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return save_all_tracks(all_data)

def mark_topic_completed(username: str, track_id: str, topic_name: str) -> Tuple[bool, str]:
    all_data = {}
    if TRACKS_FILE.exists():
        try:
            with open(TRACKS_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception:
            pass
    clean_user = (username or "ardont").strip().lower()
    u_data = all_data.setdefault(clean_user, {"tracks": []})
    
    for t in u_data.get("tracks", []):
        if t.get("id") == track_id or track_id.lower() in t.get("title", "").lower():
            for top in t.get("topics", []):
                if topic_name.lower() in top.get("name", "").lower():
                    top["completed"] = True
                    total = len(t.get("topics", []))
                    comp = sum(1 for x in t.get("topics", []) if x.get("completed"))
                    t["progress_percent"] = int((comp / total) * 100) if total > 0 else 100
                    save_all_tracks(all_data)
                    return True, f"Тема '{top.get('name')}' в треке '{t.get('title')}' отмечена выполненной! Прогресс: {t['progress_percent']}%"
    return False, "Тема или трек не найдены."
