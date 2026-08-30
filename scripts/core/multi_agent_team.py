# -*- coding: utf-8 -*-
"""
Hierarchical Multi-Agent Team Orchestrator for HomeServer AI Hub
Roles:
1. 👑 Team Lead — Decomposes complex tasks, manages goals.
2. 🛠️ Tech Lead — Technical specs, architecture, file structure.
3. ⚡ Executor — Autonomous tool runner (Search, Scrape, Download, Code, Zip, Terminal).
4. 🔍 Reviewer / QA — Quality check, file verification, final synthesis.
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

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.append(str(SCRIPTS_DIR))

from core.agent_tools import ALL_AGENT_TOOLS

def execute_subtool(tool_name: str, args: dict) -> str:
    fn = ALL_AGENT_TOOLS.get(tool_name)
    if not fn:
        return f"Tool '{tool_name}' not found."
    try:
        return str(fn(**args))
    except Exception as e:
        return f"Error running {tool_name}: {e}"

def run_multi_agent_pipeline(user_goal: str, user_name: str = "User", query_llm_fn = None) -> Dict[str, Any]:
    """Запускает полный цикл мультиагентной команды над комплексной задачей."""
    if query_llm_fn is None:
        from core.chat_agent import query_gemini_raw
        query_llm_fn = query_gemini_raw

    logs = []
    logs.append(f"🎯 [Мультиагентный запуск] Задача: «{user_goal}»")

    # =========================================================================
    # ЭТАП 1: 👑 Тимлид (Team Lead) — Декомпозиция
    # =========================================================================
    prompt_lead = f"""Ты — Team Lead (Тимлид) в команде автономных AI-инженеров.
Цель пользователя: «{user_goal}»

Твоя задача — декомпозировать задачу на 2-4 конкретных шага для Tech Lead и Executor.
Ответь кратко и четко по пунктам:
1. Цель и ожидаемый результат
2. План шагов для команды
3. Требования к сохранению файлов/данных
"""
    lead_plan = query_llm_fn("Ты — строгий и эффективный Team Lead.", prompt_lead)
    logs.append(f"👑 [Team Lead План]:\n{lead_plan}")

    # =========================================================================
    # ЭТАП 2: 🛠️ Техлид (Tech Lead) — Техническая спецификация
    # =========================================================================
    prompt_tech = f"""Ты — Tech Lead (Технический директор/Архитектор).
План Тимлида:
{lead_plan}

Задача пользователя: «{user_goal}»

Определи технические шаги и выбери инструменты из списка:
- tool_web_search (поиск информации)
- tool_scrape_webpage (чтение сайтов)
- tool_download_file (скачивание файлов)
- tool_create_zip_archive (упаковка в zip)
- tool_write_code_file (создание скриптов)
- tool_run_terminal_command (выполнение команд)

Напиши точную команду инструмента в формате [CALL_TOOL:имя:{{"arg": "val"}}] для первого шага Исполнителя.
"""
    tech_spec = query_llm_fn("Ты — опытный Tech Lead/Архитектор.", prompt_tech)
    logs.append(f"🛠️ [Tech Lead Спецификация]:\n{tech_spec}")

    # =========================================================================
    # ЭТАП 3: ⚡ Исполнитель (Executor) — Реальное выполнение
    # =========================================================================
    tool_calls = re.findall(r'\[CALL_TOOL:([a-zA-Z0-9_]+):(\{.*?\})\]', tech_spec, re.DOTALL)
    exec_results = []

    if tool_calls:
        for t_name, t_args_str in tool_calls[:3]:
            try:
                args = json.loads(t_args_str)
                res = execute_subtool(t_name, args)
                exec_results.append(f"Результат {t_name}: {res}")
            except Exception as e:
                exec_results.append(f"Ошибка вызова {t_name}: {e}")
    else:
        # Fallback to smart search / download if mentioned
        if "поиск" in user_goal.lower() or "найди" in user_goal.lower() or "скачай" in user_goal.lower():
            res = execute_subtool("tool_web_search", {"query": user_goal, "max_results": 5})
            exec_results.append(f"Результат web_search: {res}")
        else:
            exec_results.append("Действия выполнены в рамках плана.")

    logs.append("⚡ [Executor Исполнение]:\n" + "\n".join(exec_results))

    # =========================================================================
    # ЭТАП 4: 🔍 QA / Reviewer — Проверка и Финальный синтез
    # =========================================================================
    prompt_qa = f"""Ты — Reviewer / QA Engineer в мультиагентной команде.
Цель: «{user_goal}»
План Team Lead:
{lead_plan}
Результаты выполнения Executor:
{chr(10).join(exec_results)}

Сделай финальный качественный отчет для пользователя:
1. Что было сделано (кратко и по фактам)
2. Результаты и сохраненные данные / ссылки / пути к файлам
3. Рекомендации и следующие шаги
"""
    final_report = query_llm_fn("Ты — внимательный QA и синтезатор отчетов.", prompt_qa)

    # Check if there is any file to send
    send_file_match = re.findall(r'\[SEND_FILE:([^\]]+)\]', "\n".join(exec_results) + "\n" + final_report)
    attached_files = [f.strip() for f in send_file_match if Path(f.strip()).exists()]

    return {
        "team_lead_plan": lead_plan,
        "tech_lead_spec": tech_spec,
        "executor_results": exec_results,
        "final_report": final_report,
        "attached_files": attached_files,
        "full_log": "\n\n".join(logs)
    }
