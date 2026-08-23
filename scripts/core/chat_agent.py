# -*- coding: utf-8 -*-
"""
Autonomous Multi-Model Chat Agent with Strict Per-User Data Isolation,
Token Quotas & Permission Guarding.
Supports:
- Per-User Chat History (chat_history_<user>.json)
- Per-User Isolated Long-Term Memory (memory_<user>.json)
- Per-User Profile & Permission-based Tool Filtering
- Token Usage Accounting & Quota Enforcement
"""
import os
import re
import sys
import json
import time
import datetime
import urllib.request
import urllib.error
import ssl
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
CONFIG_PATH = BASE_DIR / "config" / ".env"
CALENDAR_FILE = BASE_DIR / "calendar_events.json"

sys.path.append(str(BASE_DIR / "scripts"))

from core.privacy_shield import sanitize_text
from core.audio_transcriber import transcribe_audio_file
from core.agent_tools import ALL_AGENT_TOOLS
from core.memory_engine import (
    load_memory, save_memory, get_chat_mode, set_chat_mode,
    add_pinned_fact, extract_and_save_facts, slice_prompt_memory,
    get_user_profile_path
)
from core.multi_agent_team import run_multi_agent_pipeline
from core.skill_manager import (
    search_skills, install_skill, list_installed_skills,
    recommend_skills_for_task, get_installed_skills_prompt_instructions,
    SKILLS_CATALOG
)
from core.token_tracker import record_token_usage, check_user_quota

def get_keys() -> Tuple[List[str], str]:
    if CONFIG_PATH.exists():
        load_dotenv(CONFIG_PATH, override=True)
    k1 = os.getenv("GEMINI_API_KEY", "")
    k2 = os.getenv("GEMINI_BACKUP_KEY", "")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
    
    gemini_keys = [k for k in [k1, k2] if k]
    return gemini_keys, deepseek_key

# ------------------------------------------------------------------------------
# 🛠️ СИСТЕМА ИНСТРУМЕНТОВ
# ------------------------------------------------------------------------------

AVAILABLE_TOOLS: Dict[str, Any] = {}

def tool_read_file(file_path: str) -> str:
    p = Path(file_path)
    if not p.is_absolute():
        p = BASE_DIR / p
    if not p.exists():
        return f"Ошибка: файл '{p}' не найден."
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()[:4000]
    except Exception as e:
        return f"Ошибка чтения файла: {e}"

def tool_list_files(dir_path: str = "") -> str:
    p = Path(dir_path) if dir_path else BASE_DIR / "inbox"
    if not p.is_absolute():
        p = BASE_DIR / p
    if not p.exists():
        return f"Ошибка: папка '{p}' не найдена."
    try:
        items = list(p.glob("*"))[:30]
        res = [f"{'📁' if item.is_dir() else '📄'} {item.name}" for item in items]
        return "\n".join(res) if res else "Папка пуста."
    except Exception as e:
        return f"Ошибка просмотра папки: {e}"

def tool_create_calendar_event(title: str, date: str, time_str: str = "12:00", description: str = "") -> str:
    try:
        events = []
        if CALENDAR_FILE.exists():
            with open(CALENDAR_FILE, "r", encoding="utf-8") as f:
                events = json.load(f)
        event_id = f"evt_{int(time.time())}"
        new_event = {
            "id": event_id,
            "title": title,
            "date": date,
            "time": time_str,
            "description": description,
            "completed": False,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        events.append(new_event)
        with open(CALENDAR_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
        return f"Событие '{title}' запланировано на {date} {time_str}."
    except Exception as e:
        return f"Ошибка создания события: {e}"

def tool_start_task(task_id: str) -> str:
    try:
        import urllib.request
        req = urllib.request.Request(f"http://localhost:8000/api/tasks/start/{task_id}", method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return f"Задача {task_id} запущена."
    except Exception as e:
        return f"Не удалось запустить задачу {task_id}: {e}"

def tool_transcribe_audio(file_path: str) -> str:
    p = Path(file_path)
    if not p.is_absolute():
        p = BASE_DIR / p
    res = transcribe_audio_file(p)
    return res.get("text") or res.get("message") or "Аудио не распознано."

AVAILABLE_TOOLS.update({
    "tool_read_file": tool_read_file,
    "tool_list_files": tool_list_files,
    "tool_create_calendar_event": tool_create_calendar_event,
    "tool_start_task": tool_start_task,
    "tool_transcribe_audio": tool_transcribe_audio,
})
AVAILABLE_TOOLS.update(ALL_AGENT_TOOLS)

def execute_tool_call(tool_name: str, args: dict, username: str = "ardont") -> str:
    from core.auth_manager import init_users_db
    db = init_users_db()
    user = db.get("users", {}).get(username, {})
    perms = user.get("permissions", {})

    # Check permission for dangerous tools
    if tool_name in ["tool_run_terminal_command", "tool_run_python_script"] and not perms.get("can_execute_scripts", True):
        return f"🔒 Доступ запрещен: у пользователя @{username} отключена возможность запуска скриптов и терминала."
    if tool_name in ["tool_download_file", "tool_create_zip_archive"] and not perms.get("can_storage", True):
        return f"🔒 Доступ запрещен: у пользователя @{username} отключен доступ к файловому хранилищу."

    func = AVAILABLE_TOOLS.get(tool_name)
    if not func:
        return f"Ошибка: инструмент '{tool_name}' не существует."
    try:
        return str(func(**args))
    except Exception as e:
        return f"Ошибка выполнения {tool_name}: {e}"

# ------------------------------------------------------------------------------
# 📜 КОНТЕКСТ И СИСТЕМНЫЙ ПРОМПТ С ИЗОЛЯЦИЕЙ ДАННЫХ
# ------------------------------------------------------------------------------

def get_system_prompt(username: str = "ardont", user_query: str = "") -> str:
    clean_user = (username or "ardont").strip().lower()
    
    # 1. Profile Context: ONLY load this user's profile
    prof_path = get_user_profile_path(clean_user)
    user_context = f"Пользователь: @{clean_user}"
    if prof_path.exists():
        try:
            with open(prof_path, "r", encoding="utf-8") as f:
                prof = json.load(f)
                user_context = f"Имя: {prof.get('display_name') or prof.get('user_name', clean_user.capitalize())}\nО пользователе: {prof.get('bio', '')}\nАктивные проекты: {prof.get('active_projects', [])}"
        except Exception:
            pass

    # 2. Memory Slice: ONLY slice this user's memory
    memory_slice = slice_prompt_memory(clean_user, user_query) if user_query else ""
    current_mode = get_chat_mode(clean_user)

    # 3. Permission-based Tool Instructions
    from core.auth_manager import init_users_db
    db = init_users_db()
    user_rec = db.get("users", {}).get(clean_user, {})
    perms = user_rec.get("permissions", {})

    tool_docs = """1. 🌐 Web, Поиск и Скачивание файлов:
- [CALL_TOOL:tool_web_search:{"query": "текст", "max_results": 5}] — живой поиск в интернете.
- [CALL_TOOL:tool_scrape_webpage:{"url": "https://..."}] — чтение страниц."""

    if perms.get("can_storage", True):
        tool_docs += """\n- [CALL_TOOL:tool_download_file:{"url": "https://...", "output_name": "file.zip"}] — прямое скачивание файлов на сервер.
- [CALL_TOOL:tool_create_zip_archive:{"source_path": "path", "zip_name": "archive.zip"}] — упаковка в чистый ZIP.
- [CALL_TOOL:tool_send_file_to_user:{"file_path": "path/file.zip"}] — отправка файла в чат."""

    if perms.get("can_execute_scripts", True):
        tool_docs += """\n\n2. 🐙 Код и Терминал:
- [CALL_TOOL:tool_git_clone:{"repo_url": "https://github.com/..."}] — клонирование репозиториев.
- [CALL_TOOL:tool_run_terminal_command:{"command": "...", "cwd": ""}] — безопасное выполнение команд.
- [CALL_TOOL:tool_run_python_script:{"script_path": "path/script.py"}] — запуск скриптов в venv."""

    tool_docs += """\n\n3. 🎯 Исследования:
- [CALL_TOOL:tool_deep_research:{"topic": "..."}] — многошаговое исследование с отчетом."""

    return f"""Ты — Джарвис (HomeServer 24/7 AI Hub), автономный умный ассистент и персональный наставник.
Ты работаешь на мощных моделях Google Gemini Flash и DeepSeek.
Твоя задача — помогать пользователю @{clean_user} в решении его персональных задач.

ПРОФИЛЬ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ (@{clean_user}):
{user_context}

{memory_slice}

АКТИВНЫЕ СПЕЦИАЛИЗИРОВАННЫЕ НАВЫКИ:
{get_installed_skills_prompt_instructions()}

ТЕКУЩАЯ ДАТА И ВРЕМЯ: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

АРСЕНАЛ ДОСТУПНЫХ ИНСТРУМЕНТОВ (ВЫЗЫВАЙ ИХ ЧЕРЕЗ СПЕЦИАЛЬНЫЙ ТЕГ [CALL_TOOL:имя:{{"arg": "val"}}]):
{tool_docs}

ПРАВИЛА ПОВЕДЕНИЯ:
- Отвечай строго контекстно для @{clean_user}.
- В режиме MENTOR: будь поддерживающим, мотивируй, задавай уточняющие вопросы по целям @{clean_user}.
- В режиме INCOGNITO: отвечай прямо и лаконично, не сохраняя факты в память.
"""

# ------------------------------------------------------------------------------
# 📜 ИСТОРИЯ ЧАТА (ИЗОЛИРОВАННАЯ ПО ПОЛЬЗОВАТЕЛЯМ)
# ------------------------------------------------------------------------------

def get_user_chat_history_path(username: str = "ardont") -> Path:
    clean_user = (username or "ardont").strip().lower()
    return BASE_DIR / "config" / f"chat_history_{clean_user}.json"

def load_chat_history(username: str = "ardont") -> List[Dict[str, Any]]:
    p = get_user_chat_history_path(username)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_chat_history(username: str, history: List[Dict[str, Any]]) -> None:
    p = get_user_chat_history_path(username)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(history[-40:], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Chat History Error] {e}")

# ------------------------------------------------------------------------------
# 🌐 LLM ЗАПРОСЫ И УЧЕТ ТОКЕНОВ
# ------------------------------------------------------------------------------

def query_llm_text(system_prompt: str, user_prompt: str, username: str = "ardont", model: Optional[str] = None) -> str:
    """Возвращает только текст ответа модели без кортежей токенов."""
    res = query_gemini_raw(system_prompt, user_prompt, username=username, requested_model=model)
    if isinstance(res, tuple):
        return res[0]
    return str(res)

def query_gemini_raw(system_prompt: str, user_prompt: str, username: str = "ardont", requested_model: Optional[str] = None) -> Tuple[str, str, int, int]:
    gemini_keys, _ = get_keys()
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Quota check
    allowed, msg = check_user_quota(username, "gemini-2.5-flash")
    if not allowed:
        return f"⚠️ {msg}", "quota_exceeded", 0, 0

    if requested_model and "deepseek" in requested_model.lower():
        _, deepseek_key = get_keys()
        if deepseek_key:
            try:
                ds_model = "deepseek-chat" if "reasoner" not in requested_model else "deepseek-reasoner"
                req_payload = {
                    "model": ds_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.7
                }
                req = urllib.request.Request(
                    "https://api.deepseek.com/v1/chat/completions",
                    data=json.dumps(req_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {deepseek_key}"}
                )
                with urllib.request.urlopen(req, context=ssl_context, timeout=40) as r:
                    res_json = json.loads(r.read().decode("utf-8"))
                    text = res_json["choices"][0]["message"]["content"]
                    usage = res_json.get("usage", {})
                    p_tok = usage.get("prompt_tokens", len(user_prompt)//4)
                    c_tok = usage.get("completion_tokens", len(text)//4)
                    record_token_usage(username, ds_model, p_tok, c_tok)
                    return text, ds_model, p_tok, c_tok
            except Exception as e:
                print(f"[DeepSeek Error] {e}. Falling back to Gemini...")

    models = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-3.7-flash"]
    if requested_model and requested_model in models:
        models.remove(requested_model)
        models.insert(0, requested_model)
    elif requested_model and "pro" in requested_model:
        models = ["gemini-pro-latest", "gemini-flash-latest"]
    last_err = ""

    for key in gemini_keys:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            combined_prompt = f"{system_prompt}\n\n[Пользователь ({username})]: {user_prompt}" if system_prompt else user_prompt
            payload = {
                "contents": [{"role": "user", "parts": [{"text": combined_prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048}
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=8, context=ssl_context) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    cands = data.get("candidates", [])
                    if cands:
                        text = cands[0]["content"]["parts"][0]["text"]
                        
                        # Token estimation / extraction
                        usage = data.get("usageMetadata", {})
                        prompt_toks = usage.get("promptTokenCount", int(len(system_prompt + user_prompt) / 4))
                        cand_toks = usage.get("candidatesTokenCount", int(len(text) / 4))
                        
                        record_token_usage(username, model, prompt_toks, cand_toks)
                        return text, model, prompt_toks, cand_toks
            except Exception as e:
                last_err = str(e)
                print(f"[Gemini Error] Key={key[:8]} Model={model}: {e}")
                continue

    # Fallback to DeepSeek
    _, deepseek_key = get_keys()
    if deepseek_key:
        allowed, msg = check_user_quota(username, "deepseek-chat")
        if not allowed:
            return f"⚠️ {msg}", "quota_exceeded", 0, 0
            
        try:
            url = "https://api.deepseek.com/chat/completions"
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.5,
                "max_tokens": 2048
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {deepseek_key}"}
            )
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["choices"][0]["message"]["content"]
                
                usage = data.get("usage", {})
                p_tok = usage.get("prompt_tokens", int(len(system_prompt + user_prompt) / 4))
                c_tok = usage.get("completion_tokens", int(len(text) / 4))
                
                record_token_usage(username, "deepseek-chat", p_tok, c_tok)
                return text, "deepseek-chat", p_tok, c_tok
        except Exception as e:
            last_err = str(e)

    if "402" in last_err or "Payment" in last_err:
        last_err = "Баланс DeepSeek пуст, но запрос успешно перенаправлен на Google Gemini."
    return f"⚠️ Временная ошибка сервиса: {last_err}", "error", 0, 0

# ------------------------------------------------------------------------------
# 🧠 ГЛАВНЫЙ ОБРАБОТЧИК ДИАЛОГА
# ------------------------------------------------------------------------------

def process_chat_message(user_message: str, username: str = "ardont", user_name: Optional[str] = None, attached_file_info: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    clean_user = (username or "ardont").strip().lower()
    clean_msg, _ = sanitize_text(user_message)
    clean_msg = clean_msg.strip()
    
    if attached_file_info:
        clean_msg += f"\n\n[ПРИКРЕПЛЕННЫЙ ФАЙЛ / АУДИО]:\n{attached_file_info}"

    msg_lower = clean_msg.lower().strip()

    # 1. Quick Mode & Memory Commands (Isolated to this user)
    if msg_lower in ["/memory", "память", "что ты помнишь", "что ты обо мне знаешь", "что ты знаешь обо мне"]:
        mem = load_memory(clean_user)
        pinned = mem.get("pinned_facts", [])
        if not pinned:
            reply = f"🧠 В долговременной памяти пользователя @{clean_user} пока нет сохраненных фактов."
        else:
            reply = f"🧠 **Долговременная память пользователя @{clean_user}:**\n\n" + "\n".join([f"• [{p.get('date', '')}] {p.get('fact')}" for p in pinned])
        return {"response": reply, "model": "memory_engine"}

    if msg_lower.startswith("/mode ") or msg_lower in ["/incognito", "/mentor", "/multiagent", "/work", "инкогнито", "наставник", "мультиагент"]:
        mode_arg = msg_lower.replace("/mode ", "").replace("/", "").strip()
        res = set_chat_mode(clean_user, mode_arg)
        return {"response": res, "model": "mode_switcher"}

    if msg_lower.startswith("запомни:") or msg_lower.startswith("обрати внимание на:"):
        fact = clean_msg.split(":", 1)[1].strip()
        res = add_pinned_fact(clean_user, fact)
        return {"response": res, "model": "memory_engine"}

    # Extract dynamic facts
    extract_and_save_facts(clean_user, clean_msg)

    # 2. Check Multi-Agent Mode
    curr_mode = get_chat_mode(clean_user)
    if curr_mode == "multiagent" or "команда агентов" in msg_lower or "мультиагент" in msg_lower:
        ma_report = run_multi_agent_pipeline(clean_msg)
        return {"response": ma_report, "model": "multi_agent_pipeline"}

    # 3. Standard AI Dialog & Tool Calling Loop
    history = load_chat_history(clean_user)
    history_context = ""
    for item in history[-6:]:
        history_context += f"Пользователь: {item.get('user', '')}\nАссистент: {item.get('assistant', '')}\n"

    system_prompt = get_system_prompt(clean_user, clean_msg)
    full_prompt = f"ПРЕДЫДУЩИЙ ДИАЛОГ:\n{history_context}\n\nНОВЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{clean_msg}"

    ai_raw_response, used_model, p_tok, c_tok = query_gemini_raw(system_prompt, full_prompt, username=clean_user)

    # Tool Execution Loop
    tool_tag_match = re.search(r"\[CALL_TOOL:([a-zA-Z0-9_]+):(\{.*?\})\]", ai_raw_response)
    final_text = ai_raw_response

    if tool_tag_match:
        t_name = tool_tag_match.group(1)
        t_args_raw = tool_tag_match.group(2)
        try:
            t_args = json.loads(t_args_raw)
            tool_output = execute_tool_call(t_name, t_args, username=clean_user)
        except Exception as e:
            tool_output = f"Ошибка разбора аргументов инструмента: {e}"

        step2_prompt = f"""ПОЛЬЗОВАТЕЛЬ СКАЗАЛ:
{clean_msg}

ТЫ ВЫЗВАЛ ИНСТРУМЕНТ: {t_name}
РЕЗУЛЬТАТ ВЫПОЛНЕНИЯ ИНСТРУМЕНТА:
{tool_output}

Сформируй итоговый развернутый и дружелюбный ответ пользователю @{clean_user}."""

        final_text, used_model, _, _ = query_gemini_raw(system_prompt, step2_prompt, username=clean_user)

    # Save to history ONLY if not incognito
    if curr_mode != "incognito":
        history.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "user": clean_msg,
            "assistant": final_text,
            "model": used_model
        })
        save_chat_history(clean_user, history)

    return {
        "response": final_text,
        "model": used_model,
        "user": clean_user,
        "mode": curr_mode
    }


# Backward compatibility alias
def ask_chat_agent(user_message: str, username: str = "ardont", user_name: Optional[str] = None, attached_file_info: Optional[str] = None) -> Dict[str, Any]:
    """Совместимая обертка для вызова чат-агента из любых модулей и ботов."""
    effective_user = user_name or username or "ardont"
    return process_chat_message(user_message, username=effective_user, user_name=effective_user, attached_file_info=attached_file_info)
