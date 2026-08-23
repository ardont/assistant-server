# -*- coding: utf-8 -*-
"""
Proactive AI Mentor & Accountability Engine for HomeServer AI Hub
Periodically initiates conversations with the user in VK / MAX / Push:
- 🌅 Morning Kick-Off: asks for plans, focus topics, offers research/tooling prep.
- ☀️ Midday Check-In: asks about progress, thoughts, blockers.
- 🌙 Evening Reflection: summaries, achievements, planning next steps.
"""
import os
import sys
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
CONFIG_DIR = BASE_DIR / "config"
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.append(str(SCRIPTS_DIR))

from core.memory_engine import load_memory, save_memory
from core.notifier import send_push, log_event

def get_mentor_dialog_prompt(slot: str, user_name: str = "User") -> str:
    from core.chat_agent import query_llm_text
    from core.study_planner import load_daily_plan
    
    plan = load_daily_plan()
    topic = plan.get("topic", "Data Science & Python") if plan else "Data Science & Python"

    prompts = {
        "morning": f"Ты — личный наставник и ментор пользователя {user_name}. Наступило утро. Тема дня: {topic}. Напиши теплое, мотивирующее и краткое (2-3 предложения) сообщение: спроси, какие мысли и планы на сегодня, и предложи помощь в поиске материалов или подготовке софта.",
        "midday": f"Ты — личный наставник пользователя {user_name}. Сейчас середина рабочего дня. Напиши краткое и дружелюбное сообщение: поинтересуйся, как продвигается работа над задачами, с какими сложностями столкнулся и не нужно ли что-то найти/скачать.",
        "evening": f"Ты — личный наставник пользователя {user_name}. Наступил вечер. Напиши краткое поддерживающее сообщение: предложи подвести итоги дня, спроси, что удалось сделать и какие инсайты появились."
    }
    
    prompt = prompts.get(slot, prompts["morning"])
    sys_inst = "Ты — чуткий, умный и вдохновляющий личный ментор-наставник в сфере IT и учебы."
    try:
        return query_llm_text(sys_inst, prompt)
    except Exception as e:
        fallback = {
            "morning": f"🌅 Доброе утро! Как настрой на сегодня? Какая главная задача в фокусе?",
            "midday": f"☀️ Привет! Как продвигается рабочий процесс? Есть ли вопросы или задачи, которые нужно разобрать?",
            "evening": f"🌙 Добрый вечер! Как прошел день? Что сегодня удалось сделать?"
        }
        return fallback.get(slot, "Привет! Как твои дела и успехи?")

def check_and_send_proactive_checkin(force_slot: str = "") -> Optional[str]:
    """Проверяет расписание и отправляет проактивное сообщение от наставника."""
    mem = load_memory()
    settings = mem.get("proactive_mentor_settings", {})
    if not settings.get("enabled", True) and not force_slot:
        return None

    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    hour = now.hour

    slot_to_trigger = ""
    if force_slot:
        slot_to_trigger = force_slot
    elif hour >= settings.get("morning_hour", 9) and hour < 12 and settings.get("last_morning_date") != today_str:
        slot_to_trigger = "morning"
        settings["last_morning_date"] = today_str
    elif hour >= settings.get("midday_hour", 14) and hour < 17 and settings.get("last_midday_date") != today_str:
        slot_to_trigger = "midday"
        settings["last_midday_date"] = today_str
    elif hour >= settings.get("evening_hour", 20) and hour < 23 and settings.get("last_evening_date") != today_str:
        slot_to_trigger = "evening"
        settings["last_evening_date"] = today_str

    if not slot_to_trigger:
        return None

    mem["proactive_mentor_settings"] = settings
    save_memory(mem)

    # Generate message
    msg = get_mentor_dialog_prompt(slot_to_trigger)
    log_event("PROACTIVE_MENTOR", f"Слот: {slot_to_trigger} -> {msg}")

    # 1. Push via ntfy
    slot_titles = {"morning": "🌅 Утренний старт", "midday": "☀️ Дневной чекап", "evening": "🌙 Вечерняя рефлексия"}
    send_push(slot_titles.get(slot_to_trigger, "🎓 AI-Наставник"), msg, priority="default", tags="mortar_board")

    # 2. Send via VK Bot if active
    try:
        from core.vk_bot import get_vk_config, send_vk_message
        token, user_id, _ = get_vk_config()
        clean_uid = str(user_id).strip().strip("'\"")
        if token and clean_uid.isdigit():
            send_vk_message(int(clean_uid), f"🎓 [AI-Наставник]\n\n{msg}", token)
    except Exception as e:
        print(f"[Proactive Mentor VK Error]: {e}")

    return msg
