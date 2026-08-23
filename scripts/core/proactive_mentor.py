# -*- coding: utf-8 -*-
"""
Proactive AI Mentor & Growth Accountability Engine for HomeServer AI Hub (Jarvis)
Initiates personalized check-ins with @ardont in VK / Push:
- 🌅 Morning Kick-Off (09:00 - 11:00): Today's focus topics, motivation, mini-quiz question for ШАД.
- ☀️ Midday Check-In (14:00 - 16:00): Progress on current tasks, intermediate results, blocker analysis.
- 🌙 Evening Reflection (21:00 - 23:00): Daily recap, recording completed milestones, planning next day.
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
from core.growth_tracker import load_user_tracks, get_tracks_summary_for_prompt
from core.notifier import send_push, log_event

def get_mentor_dialog_prompt(slot: str, username: str = "ardont") -> str:
    clean_user = (username or "ardont").strip().lower()
    from core.chat_agent import query_llm_text
    
    tracks_info = get_tracks_summary_for_prompt(clean_user)

    prompts = {
        "morning": f"""Ты — Джарвис, персональный наставник и ментор Сергея (@{clean_user}).
{tracks_info}

Сейчас утро. Напиши бодрое, вдохновляющее и четкое утреннее сообщение в ВК:
1. Поприветствуй Сергея по имени.
2. Напомни главный фокус дня по подготовке в ШАД или разработке HomeServer.
3. Задай 1 короткий, интересный вопрос/задачку для разминки ума (по линейной алгебре, теории вероятностей или ML) или спроси, во сколько планирует начать занятия.
Сделай сообщение живым, кратким (до 4-5 предложений) и с аккуратными эмодзи.""",

        "midday": f"""Ты — Джарвис, ментор Сергея (@{clean_user}).
{tracks_info}

Сейчас середина дня. Напиши краткий дружелюбный чекап в ВК:
1. Спроси, как идет прогресс по сегодняшнему фокусу.
2. Уточни, есть ли непонятные темы или затыки, по которым нужно сгенерировать Study Guide через NotebookLM или написать скрипт.
3. Подбодри двигаться вперед.""",

        "evening": f"""Ты — Джарвис, ментор Сергея (@{clean_user}).
{tracks_info}

Сейчас вечер. Напиши сообщение для подведения итогов дня в ВК:
1. Узнай, что сегодня удалось разобрать и закрыть из тем (предложи написать `/done <название темы>`, чтобы отметить прогресс).
2. Кратко резюмируй ценность сегодняшних усилий для поступления в ШАД и развития проектов.
3. Пожелай отличного отдыха."""
    }

    prompt = prompts.get(slot, prompts["morning"])
    sys_inst = f"Ты — Джарвис, личный наставник и умный ментор Сергея (@{clean_user}) по Data Science, ШАД и разработке."
    try:
        res = query_llm_text(sys_inst, prompt, username=clean_user)
        if res and "⚠️" not in res:
            return res
    except Exception as e:
        print(f"[Proactive Mentor Error]: {e}")

    fallbacks = {
        "morning": f"🌅 Доброе утро, Сергей! Джарвис на связи. Главный фокус сегодня: подготовка к ШАД (Линейная алгебра/SVD) и запуск Antigravity дашборда. С чего планируешь начать?",
        "midday": f"☀️ Привет! Как продвигаются задачи по ШАД и коду? Нужна ли помощь или свежий Study Guide по текущей теме?",
        "evening": f"🌙 Добрый вечер! Как прошел день? Напиши, что удалось разобрать или выполни команду /done <тема>, чтобы я зафиксировал твой прогресс в треках!"
    }
    return fallbacks.get(slot, "Привет, Сергей! Как успехи в учебе и проектах?")

def check_and_send_proactive_checkin(force_slot: str = "", username: str = "ardont") -> Optional[str]:
    """Проверяет расписание и отправляет проактивное сообщение от наставника в ВК."""
    clean_user = (username or "ardont").strip().lower()
    mem = load_memory(clean_user)
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
    save_memory(clean_user, mem)

    msg = get_mentor_dialog_prompt(slot_to_trigger, username=clean_user)
    log_event("INFO", "PROACTIVE_MENTOR", f"Слот: {slot_to_trigger} -> {msg}")

    # 1. Push via ntfy
    slot_titles = {"morning": "🌅 Утренний старт", "midday": "☀️ Дневной чекап", "evening": "🌙 Вечерняя рефлексия"}
    send_push(slot_titles.get(slot_to_trigger, "🎓 Джарвис Ментор"), msg, priority="default", tags="mortar_board")

    # 2. Send via VK Bot to 816140871
    try:
        from core.vk_bot import get_vk_config, send_vk_message
        token, user_id, _ = get_vk_config()
        clean_uid = str(user_id).strip().strip("'\"")
        if token and clean_uid.isdigit():
            send_vk_message(int(clean_uid), f"🎓 [Джарвис • Наставник]\n\n{msg}", token)
            print(f"[Proactive Mentor] Sent {slot_to_trigger} message to VK user {clean_uid}")
    except Exception as e:
        print(f"[Proactive Mentor VK Error]: {e}")

    return msg
