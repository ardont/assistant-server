# -*- coding: utf-8 -*-
"""
Duolingo-Style Daily AI Quiz & Flashcard Trainer for HomeServer
Generates interactive daily quizzes on Math, Python, Algorithms, and SHAD.
Tracks streaks, XP, levels, and user progress.
"""
import os
import sys
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / ".env"
PROFILE_PATH = BASE_DIR / "config" / "user_profile.json"
QUIZ_FILE = BASE_DIR / "quiz_progress.json"

if CONFIG_PATH.exists():
    load_dotenv(CONFIG_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def load_quiz_state() -> Dict[str, Any]:
    if not QUIZ_FILE.exists():
        state = {
            "streak_days": 1,
            "last_active_date": datetime.date.today().strftime("%Y-%m-%d"),
            "xp": 50,
            "level": 1,
            "today_completed": False,
            "current_quiz": []
        }
        save_quiz_state(state)
        return state
    try:
        with open(QUIZ_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            # Streak check
            last_date_str = state.get("last_active_date", "")
            if last_date_str:
                last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
                delta = (datetime.date.today() - last_date).days
                if delta == 1:
                    pass # streak maintained
                elif delta > 1:
                    state["streak_days"] = 0 # broken streak
                if delta >= 1:
                    state["today_completed"] = False
            return state
    except Exception:
        return {"streak_days": 0, "xp": 0, "level": 1, "today_completed": False, "current_quiz": []}

def save_quiz_state(state: Dict[str, Any]):
    try:
        with open(QUIZ_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving quiz state: {e}")

def generate_daily_quiz(force_new: bool = False) -> List[Dict[str, Any]]:
    state = load_quiz_state()
    if not force_new and state.get("current_quiz") and not state.get("today_completed"):
        return state["current_quiz"]

    # Generate 3 bite-sized questions via Gemini based on user topics
    user_context = "Data Science, высшая математика (линейная алгебра, матанализ, тервер), Python, алгоритмы, поступление в ШАД."
    if PROFILE_PATH.exists():
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                prof = json.load(f)
                user_context = f"{prof.get('bio', '')}, проекты: {prof.get('active_projects', [])}"
        except Exception:
            pass

    prompt = f"""
Создай ровно 3 коротких, интересных вопроса в стиле Duolingo/теста для тренировки знаний (ШАД, алгоритмы, математика, Python, ML).
Контекст ученика: {user_context}

Верни результат СТРОГО в виде чистого JSON списка без лишнего текста и без кавычек ```json:
[
  {{
    "id": 1,
    "topic": "Линейная алгебра / ШАД",
    "question": "Короткий вопрос (до 2 строк)",
    "options": ["Вариант A", "Вариант B", "Вариант C", "Вариант D"],
    "correct_index": 0,
    "explanation": "Короткое и понятное объяснение почему этот ответ верный."
  }},
  {{
    "id": 2,
    "topic": "Python / Алгоритмы",
    "question": "Короткий вопрос",
    "options": ["Вариант A", "Вариант B", "Вариант C", "Вариант D"],
    "correct_index": 1,
    "explanation": "Объяснение."
  }},
  {{
    "id": 3,
    "topic": "Теория вероятностей / ML",
    "question": "Короткий вопрос",
    "options": ["Вариант A", "Вариант B", "Вариант C", "Вариант D"],
    "correct_index": 2,
    "explanation": "Объяснение."
  }}
]
"""
    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt
        )
        txt = response.text.strip()
        if txt.startswith("```json"):
            txt = txt[7:]
        if txt.startswith("```"):
            txt = txt[3:]
        if txt.endswith("```"):
            txt = txt[:-3]
        txt = txt.strip()
        quiz_data = json.loads(txt)
        state["current_quiz"] = quiz_data
        save_quiz_state(state)
        return quiz_data
    except Exception as e:
        # Fallback offline quiz
        fallback = [
            {
                "id": 1,
                "topic": "Python & Алгоритмы",
                "question": "Какова средняя амортизированная сложность вставки элемента в конец Python list (`list.append`)?",
                "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"],
                "correct_index": 0,
                "explanation": "Python резервирует память с запасом (over-allocation), поэтому амортизированное время добавления в конец — O(1)."
            },
            {
                "id": 2,
                "topic": "Линейная алгебра (ШАД)",
                "question": "Чему равен определитель матрицы A, если det(A^-1) = 4?",
                "options": ["4", "0.25", "-4", "16"],
                "correct_index": 1,
                "explanation": "По свойству определителей det(A^-1) = 1 / det(A), следовательно det(A) = 1 / 4 = 0.25."
            },
            {
                "id": 3,
                "topic": "Теория вероятностей",
                "question": "Брошены 2 правильные игральные кости. Какова вероятность того, что сумма очков равна 7?",
                "options": ["1/12", "1/6", "1/36", "7/36"],
                "correct_index": 1,
                "explanation": "Всего 36 исходов. Сумму 7 дают 6 пар: (1,6),(2,5),(3,4),(4,3),(5,2),(6,1). Итого: 6/36 = 1/6."
            }
        ]
        state["current_quiz"] = fallback
        save_quiz_state(state)
        return fallback

def submit_quiz_answer(question_id: int, selected_index: int) -> Dict[str, Any]:
    state = load_quiz_state()
    quiz = state.get("current_quiz", [])
    target = next((q for q in quiz if q["id"] == question_id), None)
    if not target:
        return {"error": "Вопрос не найден"}

    is_correct = (selected_index == target["correct_index"])
    reward_xp = 15 if is_correct else 2
    state["xp"] = state.get("xp", 0) + reward_xp
    state["level"] = 1 + (state["xp"] // 100)
    save_quiz_state(state)

    return {
        "is_correct": is_correct,
        "correct_index": target["correct_index"],
        "explanation": target.get("explanation", ""),
        "earned_xp": reward_xp,
        "total_xp": state["xp"],
        "level": state["level"]
    }

def complete_daily_quiz() -> Dict[str, Any]:
    state = load_quiz_state()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if state.get("last_active_date") != today_str:
        state["streak_days"] = state.get("streak_days", 0) + 1
        state["last_active_date"] = today_str
    state["today_completed"] = True
    state["xp"] = state.get("xp", 0) + 50 # Bonus streak XP
    state["level"] = 1 + (state["xp"] // 100)
    save_quiz_state(state)
    return {
        "streak_days": state["streak_days"],
        "total_xp": state["xp"],
        "level": state["level"]
    }


def generate_quiz_question() -> Dict[str, Any]:
    """Returns a single active quiz question for bots and quick tests."""
    quiz_list = generate_daily_quiz()
    if quiz_list and len(quiz_list) > 0:
        return quiz_list[0]
    return {
        "question": "Какова сложность поиска элемента в хэш-таблице в среднем?",
        "options": ["O(1)", "O(log n)", "O(n)", "O(n^2)"],
        "correct_index": 0,
        "explanation": "В среднем хэш-таблица обеспечивает поиск за константное время O(1)."
    }

def check_quiz_answer(question_idx: int, selected_idx: int) -> Dict[str, Any]:
    return submit_quiz_answer(question_idx, selected_idx)
