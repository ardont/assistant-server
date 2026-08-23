# -*- coding: utf-8 -*-
"""
Token Usage Accounting & Quota Manager for HomeServer AI Hub
Tracks prompt tokens, completion tokens, costs and limits per user and per model.
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
CONFIG_DIR = BASE_DIR / "config"
TOKEN_STATS_FILE = CONFIG_DIR / "token_stats.json"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def load_token_stats() -> Dict[str, Any]:
    if not TOKEN_STATS_FILE.exists():
        initial = {
            "users": {},
            "total_tokens_all_time": 0,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        save_token_stats(initial)
        return initial
    try:
        with open(TOKEN_STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Token Tracker] Ошибка чтения token_stats.json: {e}")
        return {"users": {}, "total_tokens_all_time": 0}

def save_token_stats(data: Dict[str, Any]) -> bool:
    try:
        data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(TOKEN_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Token Tracker] Ошибка записи token_stats.json: {e}")
        return False

def record_token_usage(username: str, model: str, prompt_tokens: int, completion_tokens: int) -> Dict[str, Any]:
    clean_user = (username or "ardont").strip().lower()
    clean_model = (model or "gemini-2.5-flash").strip()
    total = prompt_tokens + completion_tokens
    
    stats = load_token_stats()
    user_stats = stats.setdefault("users", {}).setdefault(clean_user, {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "requests_count": 0,
        "token_quota": -1 if clean_user == "ardont" else 50000, # -1 = unlimited
        "allowed_models": ["*"] if clean_user == "ardont" else ["gemini-2.5-flash", "gemini-flash-latest"],
        "models_usage": {}
    })
    
    user_stats["total_tokens"] += total
    user_stats["prompt_tokens"] += prompt_tokens
    user_stats["completion_tokens"] += completion_tokens
    user_stats["requests_count"] += 1
    
    m_stat = user_stats.setdefault("models_usage", {}).setdefault(clean_model, {
        "total_tokens": 0,
        "requests_count": 0
    })
    m_stat["total_tokens"] += total
    m_stat["requests_count"] += 1
    
    stats["total_tokens_all_time"] = stats.get("total_tokens_all_time", 0) + total
    save_token_stats(stats)
    return user_stats

def check_user_quota(username: str, model: str) -> Tuple[bool, str]:
    clean_user = (username or "ardont").strip().lower()
    if clean_user == "ardont":
        return True, "OK"  # Admin is always unlimited
        
    stats = load_token_stats()
    user_stats = stats.get("users", {}).get(clean_user)
    if not user_stats:
        return True, "OK"
        
    # Check allowed models
    allowed = user_stats.get("allowed_models", ["*"])
    if "*" not in allowed and model not in allowed:
        return False, f"Доступ к модели '{model}' ограничен администратором для @{clean_user}."
        
    # Check token quota
    quota = user_stats.get("token_quota", 50000)
    used = user_stats.get("total_tokens", 0)
    if quota != -1 and used >= quota:
        return False, f"⚠️ Лимит токенов исчерпан ({used}/{quota}). Обратитесь к администратору ardont для увеличения квоты."
        
    return True, "OK"

def set_user_quota(username: str, quota: int, allowed_models: List[str] = None) -> bool:
    clean_user = (username or "ardont").strip().lower()
    stats = load_token_stats()
    user_stats = stats.setdefault("users", {}).setdefault(clean_user, {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "requests_count": 0,
        "models_usage": {}
    })
    user_stats["token_quota"] = quota
    if allowed_models is not None:
        user_stats["allowed_models"] = allowed_models
    return save_token_stats(stats)


def remove_all_limits() -> bool:
    """Полностью снимает все квоты и открывает все модели для всех пользователей."""
    stats = load_token_stats()
    for u in stats.get("users", {}).values():
        u["token_quota"] = -1
        u["allowed_models"] = ["*"]
    return save_token_stats(stats)

def update_user_models(username: str, allowed_models: List[str]) -> bool:
    """Обновляет список доступных моделей для пользователя."""
    clean_user = (username or "ardont").strip().lower()
    stats = load_token_stats()
    user_stats = stats.setdefault("users", {}).setdefault(clean_user, {
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "requests_count": 0,
        "token_quota": -1,
        "models_usage": {}
    })
    user_stats["allowed_models"] = allowed_models if allowed_models else ["*"]
    return save_token_stats(stats)

def reset_user_tokens(username: str) -> bool:
    """Сбрасывает счетчики токенов для пользователя."""
    clean_user = (username or "ardont").strip().lower()
    stats = load_token_stats()
    if clean_user in stats.get("users", {}):
        stats["users"][clean_user]["total_tokens"] = 0
        stats["users"][clean_user]["prompt_tokens"] = 0
        stats["users"][clean_user]["completion_tokens"] = 0
        stats["users"][clean_user]["requests_count"] = 0
        stats["users"][clean_user]["models_usage"] = {}
        return save_token_stats(stats)
    return False

def delete_user_stats(username: str) -> bool:
    """Удаляет запись статистики для пользователя."""
    clean_user = (username or "ardont").strip().lower()
    stats = load_token_stats()
    if clean_user in stats.get("users", {}):
        del stats["users"][clean_user]
        return save_token_stats(stats)
    return False
