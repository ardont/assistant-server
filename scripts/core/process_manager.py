# -*- coding: utf-8 -*-
"""
Process & Script Manager Module for HomeServer
Manages execution, live monitoring, logging, and metrics of background scripts and automation tasks.
"""
import os
import sys
import time
import json
import subprocess
import threading
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path("C:/HomeServer")
CONFIG_DIR = BASE_DIR / "config"
TASKS_CONFIG = CONFIG_DIR / "tasks_registry.json"
LOGS_DIR = BASE_DIR / "logs" / "tasks"
PYTHON_EXE = str(BASE_DIR / "venv" / "Scripts" / "python.exe")

LOGS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TASKS = [
    {
        "id": "task_enable_rdp",
        "name": "🖥️ Включить RDP (Удаленный стол + Пароль 1234)",
        "description": "Включает службу Remote Desktop (порт 3389), настраивает брандмауэр и устанавливает пароль 1234 для входа",
        "command": f'"{PYTHON_EXE}" "C:/HomeServer/scripts/tasks/enable_rdp_runner.py"',
        "category": "system",
        "status": "stopped",
        "schedule": "manual"
    },
    {
        "id": "task_crypto_tracker",
        "name": "📈 Крипто-Монитор (Bitcoin & Crypto Live)",
        "description": "Периодически опрашивает CoinDesk/Binance API, отслеживает курсы криптовалют и выводит сводку",
        "command": f'"{PYTHON_EXE}" "C:/HomeServer/scripts/tasks/crypto_runner.py"',
        "category": "crypto",
        "status": "stopped",
        "schedule": "manual"
    },
    {
        "id": "task_backup_server",
        "name": "💾 Резервное копирование (Auto Backup)",
        "description": "Создает сжатый zip-архив папок data/ и config/ в C:/HomeServer/backups",
        "command": f'"{PYTHON_EXE}" "C:/HomeServer/scripts/tasks/backup_runner.py"',
        "category": "maintenance",
        "status": "stopped",
        "schedule": "manual"
    },
    {
        "id": "task_deep_scan",
        "name": "🔍 Глубокий аудит и сканирование INBOX",
        "description": "Запускает повторный анализ всех входящих файлов и генерацию отчета Gemini",
        "command": f'"{PYTHON_EXE}" "C:/HomeServer/scripts/tasks/file_ai_organizer.py"',
        "category": "ai",
        "status": "stopped",
        "schedule": "manual"
    }
]

class ProcessManager:
    def __init__(self):
        self.running_processes: Dict[str, subprocess.Popen] = {}
        self.process_logs: Dict[str, List[str]] = {}
        self.process_metrics: Dict[str, Dict[str, Any]] = {}
        self.start_times: Dict[str, float] = {}
        self.init_registry()
        
    def init_registry(self):
        if not TASKS_CONFIG.exists():
            with open(TASKS_CONFIG, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_TASKS, f, ensure_ascii=False, indent=2)
                
    def get_tasks(self) -> List[Dict[str, Any]]:
        self.init_registry()
        try:
            with open(TASKS_CONFIG, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        except Exception:
            tasks = DEFAULT_TASKS
            
        for t in tasks:
            tid = t["id"]
            if tid in self.running_processes:
                proc = self.running_processes[tid]
                poll = proc.poll()
                if poll is None:
                    t["status"] = "running"
                    t["pid"] = proc.pid
                    uptime_sec = int(time.time() - self.start_times.get(tid, time.time()))
                    t["uptime"] = f"{uptime_sec} сек"
                else:
                    t["status"] = "completed" if poll == 0 else "failed"
                    t["exit_code"] = poll
                    t["uptime"] = "Завершен"
            else:
                t["status"] = "stopped"
                t["uptime"] = "-"
                
            t["metrics"] = self.process_metrics.get(tid, {})
            logs = self.process_logs.get(tid, [])
            t["last_log"] = logs[-1] if logs else "Нет логов"
            
        return tasks

    def start_task(self, task_id: str) -> bool:
        tasks = self.get_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return False
            
        if task_id in self.running_processes and self.running_processes[task_id].poll() is None:
            return True
            
        log_file = LOGS_DIR / f"{task_id}.log"
        cmd = task["command"]
        
        self.process_logs[task_id] = []
        self.start_times[task_id] = time.time()
        
        def run_thread():
            try:
                proc = subprocess.Popen(
                    cmd,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1
                )
                self.running_processes[task_id] = proc
                
                with open(log_file, "a", encoding="utf-8") as f_out:
                    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f_out.write(f"\n--- [ЗАПУСК {ts}] ---\n")
                    
                    for line in proc.stdout:
                        line_str = line.rstrip()
                        self.process_logs.setdefault(task_id, []).append(line_str)
                        if len(self.process_logs[task_id]) > 500:
                            self.process_logs[task_id].pop(0)
                        f_out.write(line_str + "\n")
                        f_out.flush()
                        
                        if "[METRIC:" in line_str:
                            try:
                                metric_part = line_str.split("[METRIC:")[1].split("]")[0]
                                if "=" in metric_part:
                                    k, v = metric_part.split("=", 1)
                                    self.process_metrics.setdefault(task_id, {})[k.strip()] = v.strip()
                            except Exception:
                                pass
                                
                proc.wait()
            except Exception as e:
                self.process_logs.setdefault(task_id, []).append(f"Ошибка запуска: {e}")
                
        t = threading.Thread(target=run_thread, daemon=True)
        t.start()
        return True

    def stop_task(self, task_id: str) -> bool:
        if task_id in self.running_processes:
            proc = self.running_processes[task_id]
            if proc.poll() is None:
                try:
                    subprocess.run(f"taskkill /F /T /PID {proc.pid}", shell=True)
                    proc.terminate()
                except Exception:
                    pass
            del self.running_processes[task_id]
            return True
        return False

    def get_logs(self, task_id: str) -> str:
        logs = self.process_logs.get(task_id, [])
        if not logs:
            log_file = LOGS_DIR / f"{task_id}.log"
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        return f.read()[-4000:]
                except Exception:
                    return ""
        return "\n".join(logs)

    def register_custom_task(self, name: str, description: str, command: str, category: str = "custom") -> dict:
        tasks = self.get_tasks()
        task_id = f"task_custom_{int(time.time())}"
        new_task = {
            "id": task_id,
            "name": name,
            "description": description,
            "command": command,
            "category": category,
            "status": "stopped",
            "schedule": "manual"
        }
        tasks.append(new_task)
        with open(TASKS_CONFIG, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        return new_task

    def get_all_statuses(self) -> list:
        return self.get_tasks()

    def get_task_logs(self, task_id: str, lines: int = 50) -> list:
        return self.get_logs(task_id, lines)

process_manager = ProcessManager()
pm = process_manager
