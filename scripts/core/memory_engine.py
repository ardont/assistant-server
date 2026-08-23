# -*- coding: utf-8 -*-
"""
Dynamic Long-Term Memory Engine & Prompt Slicer with Strict Per-User Isolation.
Each user (ardont, maxim, etc.) has their OWN private memory (memory_<user>.json)
and profile (user_profile_<user>.json).
"""
import os
import sys
import json
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MEMORY_TEMPLATE = {
    "chat_mode": "mentor",  # "mentor", "multiagent", "work", "incognito"
    "user_preferences": {
        "format": "concise_bullet_points",
        "language": "ru",
        "proactive_checkins": True
    },
    "pinned_facts": [],
    "active_goals": [],
    "last_interaction": ""
}

def get_user_memory_path(username: str = "ardont") -> Path:
    clean_user = (username or "ardont").strip().lower()
    return CONFIG_DIR / f"memory_{clean_user}.json"

def get_user_profile_path(username: str = "ardont") -> Path:
    clean_user = (username or "ardont").strip().lower()
    user_file = CONFIG_DIR / f"user_profile_{clean_user}.json"
    if clean_user == "ardont" and not user_file.exists():
        # Fallback to existing user_profile.json for ardont
        old_prof = CONFIG_DIR / "user_profile.json"
        if old_prof.exists():
            return old_prof
    return user_file

def load_memory(username: str = "ardont") -> Dict[str, Any]:
    mem_file = get_user_memory_path(username)
    if not mem_file.exists():
        # Initialize default user memory
        mem = dict(DEFAULT_MEMORY_TEMPLATE)
        if username == "ardont":
            # For ardont migrate legacy pinned facts if present
            legacy_mem = CONFIG_DIR / "memory.json"
            if legacy_mem.exists():
                try:
                    with open(legacy_mem, "r", encoding="utf-8") as f:
                        mem = json.load(f)
                except Exception:
                    pass
        save_memory(username, mem)
        return mem
        
    try:
        with open(mem_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Memory Engine] Ошибка чтения {mem_file}: {e}")
        return dict(DEFAULT_MEMORY_TEMPLATE)

def save_memory(username: str, data: Dict[str, Any]) -> bool:
    mem_file = get_user_memory_path(username)
    try:
        data["last_interaction"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(mem_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Memory Engine] Ошибка сохранения {mem_file}: {e}")
        return False

def get_chat_mode(username: str = "ardont") -> str:
    mem = load_memory(username)
    return mem.get("chat_mode", "mentor")

def set_chat_mode(username: str, mode: str) -> str:
    valid_modes = {
        "incognito": "🕵️ Инкогнито (бытовой режим без сохранения памяти)",
        "mentor": "🎓 Личный Наставник (саморазвитие, фокус и учеба)",
        "multiagent": "👥 Мультиагентная команда (Тимлид, Техлид, Исполнитель, QA)",
        "work": "⚡ Рабочий режим (строгий лаконичный код и инструменты)"
    }
    mode_clean = mode.lower().strip()
    if mode_clean not in valid_modes:
        return f"Неизвестный режим. Доступные режимы: {', '.join(valid_modes.keys())}"
    
    mem = load_memory(username)
    mem["chat_mode"] = mode_clean
    save_memory(username, mem)
    return f"Режим диалога для @{username} переключен на: {valid_modes[mode_clean]}"

def add_pinned_fact(username: str, fact: str, category: str = "general") -> str:
    if not fact.strip():
        return "Факт не может быть пустым."
    
    mem = load_memory(username)
    facts = mem.setdefault("pinned_facts", [])
    
    # Check duplicate
    for item in facts:
        if item.get("fact", "").lower() == fact.strip().lower():
            return f"ℹ️ Этот факт уже есть в памяти пользователя @{username}: «{fact}»"
            
    new_entry = {
        "id": f"fact_{int(time.time())}",
        "fact": fact.strip(),
        "category": category,
        "date": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    facts.append(new_entry)
    save_memory(username, mem)
    return f"💾 Факт сохранён в долговременную память @{username}: «{fact.strip()}»"

def extract_and_save_facts(username: str, user_message: str) -> Optional[str]:
    clean_user = (username or "ardont").strip().lower()
    mem = load_memory(clean_user)
    if mem.get("chat_mode") == "incognito":
        return None  # Incognito mode does NOT save memory
        
    patterns = [
        r"(?:запомни|обрати внимание|зафиксируй|имей в виду|важно):\s*(.+)",
        r"(?:я планирую|я хочу сдавать|моя цель|мой фокус):\s*(.+)",
    ]
    
    for pat in patterns:
        m = re.search(pat, user_message, re.IGNORECASE)
        if m:
            fact_candidate = m.group(1).strip()
            if len(fact_candidate) > 5:
                return add_pinned_fact(clean_user, fact_candidate, category="auto_extracted")
    return None

def slice_prompt_memory(username: str = "ardont", user_query: str = "") -> str:
    clean_user = (username or "ardont").strip().lower()
    mem = load_memory(clean_user)
    mode = mem.get("chat_mode", "mentor")
    
    if mode == "incognito":
        return "РЕЖИМ: ИНКОГНИТО (бытовой запрос, долгосрочную память не использовать и не обновлять)."
        
    pinned_facts = mem.get("pinned_facts", [])
    active_goals = mem.get("active_goals", [])
    
    if not pinned_facts and not active_goals:
        return f"РЕЖИМ: {mode.upper()}. Пользователь @{clean_user} (личная память пуста)."
        
    # Keywords matching
    query_words = set(re.findall(r"\w{3,}", user_query.lower()))
    relevant_facts = []
    
    for f in pinned_facts:
        f_text = f.get("fact", "")
        f_words = set(re.findall(r"\w{3,}", f_text.lower()))
        if not query_words or (query_words & f_words):
            relevant_facts.append(f"• {f_text}")
            
    if not relevant_facts and pinned_facts:
        relevant_facts = [f"• {f.get('fact')}" for f in pinned_facts[-3:]]
        
    facts_str = "\n".join(relevant_facts)
    goals_str = "\n".join([f"🎯 {g}" for g in active_goals[:3]])
    
    res = f"РЕЖИМ ДИАЛОГА: {mode.upper()} ДЛЯ @{clean_user}\n"
    if facts_str:
        res += f"ДОЛГОВРЕМЕННАЯ ПАМЯТЬ ПОЛЬЗОВАТЕЛЯ @{clean_user}:\n{facts_str}\n"
    if goals_str:
        res += f"АКТИВНЫЕ ЦЕЛИ @{clean_user}:\n{goals_str}\n"
        
    return res.strip()
