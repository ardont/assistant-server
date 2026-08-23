# -*- coding: utf-8 -*-
"""
Smart Task Decomposition & Daily Focus Engine for HomeServer
High-Speed In-Memory RAM Caching, Multi-Key Rotation & Smart Topic Rotation.
"""
import os
import sys
import json
import threading
import datetime
import random
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path("C:/HomeServer")
CONFIG_PATH = BASE_DIR / "config" / ".env"
PROFILE_PATH = BASE_DIR / "config" / "user_profile.json"
PLAN_FILE = BASE_DIR / "daily_plan.json"
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.append(str(SCRIPTS_DIR))

def get_keys():
    if CONFIG_PATH.exists():
        load_dotenv(CONFIG_PATH, override=True)
    k1 = os.getenv("GEMINI_API_KEY", "")
    k2 = os.getenv("GEMINI_BACKUP_KEY", "")
    return [k for k in [k1, k2] if k]

from core.notifier import notify_info

_is_generating = False

SMART_TOPIC_BANK = [
    {
        "topic": "Линейная алгебра: Собственные значения и положительная определенность (ШАД)",
        "overview": "Ключевая тема для оптимизации и алгоритмов ML (PCA, SVD, квадратичные формы).",
        "tasks": [
            {"id": "t1", "title": "📖 Теория: Характеристический многочлен и критерий Сильвестра (15 мин)", "details": "Повторить свойства det(A - λI)=0 и главные миноры.", "done": False},
            {"id": "t2", "title": "✍️ Практика: Найти собственные числа блочной матрицы из ШАД (20 мин)", "details": "Разобрать задачу на диагонализацию симметричной матрицы.", "done": False},
            {"id": "t3", "title": "💻 Python: Разложение SVD и PCA через NumPy / Scipy (15 мин)", "details": "Реализовать сжатие матрицы признаков с помощью `np.linalg.svd`.", "done": False}
        ],
        "roadmap": [
            {"name": "Линейная алгебра", "progress": 70},
            {"name": "Теория вероятностей", "progress": 50},
            {"name": "Алгоритмы (ШАД)", "progress": 60},
            {"name": "Python / ML", "progress": 75}
        ]
    },
    {
        "topic": "Теория вероятностей: Условная вероятность и формула Байеса (ШАД)",
        "overview": "Базис статистического вывода, байесовских классификаторов и машинного обучения.",
        "tasks": [
            {"id": "t1", "title": "📖 Теория: Формула полной вероятности и теорема Байеса (15 мин)", "details": "Повторить формулировки и геометрический смысл условной плотности.", "done": False},
            {"id": "t2", "title": "✍️ Практика: Задача с парадоксом Монти Холла и проверкой тестов (20 мин)", "details": "Решить 2 типовые задачи на байесовское обновление априорной вероятности.", "done": False},
            {"id": "t3", "title": "💻 Python: Симуляция метода Монте-Карло для оценки P(A|B) (15 мин)", "details": "Написать скрипт генерации 100 000 случайных событий на NumPy.", "done": False}
        ],
        "roadmap": [
            {"name": "Линейная алгебра", "progress": 70},
            {"name": "Теория вероятностей", "progress": 55},
            {"name": "Алгоритмы (ШАД)", "progress": 60},
            {"name": "Python / ML", "progress": 75}
        ]
    }
]

_RAM_PLAN_CACHE: Dict[str, Any] = SMART_TOPIC_BANK[0].copy()
_RAM_PLAN_CACHE["date"] = datetime.date.today().strftime("%Y-%m-%d")

def _init_cache():
    global _RAM_PLAN_CACHE
    if PLAN_FILE.exists():
        try:
            with open(PLAN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data and isinstance(data, dict) and data.get("tasks"):
                    _RAM_PLAN_CACHE = data
                    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 💾 [ПАМЯТЬ] План загружен в RAM: '{_RAM_PLAN_CACHE.get('topic')}'")
                    return
        except Exception as e:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [!] Ошибка чтения daily_plan.json: {e}")
    save_daily_plan(_RAM_PLAN_CACHE)

_init_cache()

def load_daily_plan() -> Dict[str, Any]:
    return _RAM_PLAN_CACHE.copy()

def save_daily_plan(plan: Dict[str, Any]):
    global _RAM_PLAN_CACHE
    _RAM_PLAN_CACHE = plan.copy()
    try:
        with open(PLAN_FILE, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [!] Ошибка сохранения daily_plan.json: {e}")

def _generate_daily_plan_sync():
    global _is_generating, _RAM_PLAN_CACHE
    if _is_generating:
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⏳ [AI PLANNER] Генерация уже выполняется в фоне...")
        return
    _is_generating = True
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🧠 [AI PLANNER] Запрос к Gemini 3.6 Flash для генерации нового плана...")
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    
    user_context = "Подготовка в ШАД (Школа анализа данных), высшая математика, линейная алгебра, тервер, Python, алгоритмы, ML."
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                prof = json.load(f)
                user_context = f"{prof.get('bio', '')}, проекты: {prof.get('active_projects', [])}"
        except Exception:
            pass

    prompt = f"""
Ты — персональный ментор и методист. Твоя задача — разбить обучение и подготовку пользователя на небольшие, понятные микро-задачи на сегодня (по 15-25 минут каждая), без перегрузки.

Контекст пользователя: {user_context}

Сформируй план на сегодня СТРОГО в виде JSON без лишнего текста и без кавычек ```json:
{{
  "date": "{today_str}",
  "topic": "Название фокус-темы дня (например: Линейная алгебра: Собственные значения и векторы)",
  "overview": "Короткое резюме на 1-2 предложения о том, почему это важно и какая динамика.",
  "tasks": [
    {{
      "id": "t1",
      "title": "📖 Теория: Кратко повторить ключевые свойства (15 мин)",
      "details": "Что конкретно прочитать или вспомнить.",
      "done": false
    }},
    {{
      "id": "t2",
      "title": "✍️ Практика: Решить 1 типовую задачу из ШАД (20 мин)",
      "details": "Конкретная задача или формула для разбора.",
      "done": false
    }},
    {{
      "id": "t3",
      "title": "💻 Код / Применение: Реализация алгоритма на Python (15 мин)",
      "details": "Короткий скрипт или упражнение на NumPy / чистый Python.",
      "done": false
    }}
  ],
  "roadmap": [
    {{"name": "Линейная алгебра & Матрицы", "progress": 65}},
    {{"name": "Теория вероятностей & Статистика", "progress": 50}},
    {{"name": "Алгоритмы и структуры данных", "progress": 60}},
    {{"name": "Python & Машинное обучение", "progress": 75}}
  ]
}}
"""
    gemini_keys = get_keys()
    generated_ok = False
    
    for g_key in gemini_keys:
        try:
            from google import genai
            client = genai.Client(api_key=g_key)
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt
            )
            txt = response.text.strip()
            if "```json" in txt:
                txt = txt.split("```json")[1].split("```")[0].strip()
            elif "```" in txt:
                txt = txt.split("```")[1].split("```")[0].strip()
            plan_data = json.loads(txt)
            save_daily_plan(plan_data)
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✨ [AI PLANNER] План сгенерирован успешно: '{plan_data.get('topic')}'")
            generated_ok = True
            break
        except Exception as e:
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] [!] Planner ({g_key[:8]}...) error: {str(e)[:60]}")
            time.sleep(0.2)

    if not generated_ok:
        chosen = random.choice(SMART_TOPIC_BANK).copy()
        chosen["date"] = today_str
        save_daily_plan(chosen)
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 💡 [AI PLANNER] Использован локальный план: '{chosen.get('topic')}'")

    _is_generating = False

def trigger_plan_generation_async():
    t = threading.Thread(target=_generate_daily_plan_sync, daemon=True)
    t.start()

def toggle_task_done(task_id: str) -> Dict[str, Any]:
    plan = load_daily_plan()
    for t in plan.get("tasks", []):
        if t.get("id") == task_id:
            t["done"] = not t.get("done", False)
            status_symbol = "✓ Выполнено" if t['done'] else "☐ В процессе"
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📌 [МИКРО-ШАГ] {status_symbol}: '{t.get('title')}'")
            break
    save_daily_plan(plan)
    return plan

def send_plan_notification() -> Dict[str, Any]:
    plan = load_daily_plan()
    topic = plan.get("topic", "Учебный план на день")
    tasks = plan.get("tasks", [])
    
    tasks_text = "\n".join([f"• {'[x]' if t.get('done') else '[ ]'} {t.get('title')}" for t in tasks])
    msg = f"🎯 Тема дня: {topic}\n\nМикро-задачи:\n{tasks_text}"
    
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 📲 [PUSH] Отправка плана на телефон...")
    success = notify_info(f"План на сегодня: {topic}", msg)
    return {"success": success, "message": "Уведомление отправлено на телефон!"}


# Aliases
get_today_plan = load_daily_plan
generate_today_plan = _generate_daily_plan_sync
