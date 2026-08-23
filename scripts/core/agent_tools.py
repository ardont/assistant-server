# -*- coding: utf-8 -*-
"""
Jarvis Autonomous Tools Suite for HomeServer AI Hub
Provides Web Search, OSINT, Git Operations, Terminal Execution, LeadGen Extractor, and Deep Research Synthesizer.
All powered 100% by Cloud LLM models (Gemini Flash + DeepSeek).
"""
import os
import sys
import json
import time
import re
import csv
import urllib.request
import urllib.parse
import urllib.error
import subprocess
import socket
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path("C:/HomeServer")
PROJECTS_DIR = BASE_DIR / "projects"
LEADS_DIR = BASE_DIR / "data" / "leads"
RESEARCH_DIR = BASE_DIR / "archive" / "research"
VENV_PYTHON = BASE_DIR / "venv" / "Scripts" / "python.exe"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
LEADS_DIR.mkdir(parents=True, exist_ok=True)
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# ==============================================================================
# 1. 🌐 WEB SEARCH, SCRAPING & OSINT
# ==============================================================================

def tool_web_search(query: str, max_results: int = 5) -> str:
    """Выполняет поиск в интернете в реальном времени и возвращает заголовки, сниппеты и ссылки."""
    clean_q = query.strip()
    if not clean_q:
        return "Ошибка: пустой поисковый запрос."
    
    encoded_q = urllib.parse.quote_plus(clean_q)
    # Use DuckDuckGo HTML Lite for fast reliable scraping without API keys
    search_url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
    req = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="ignore")
            
        results = []
        # Extract results blocks
        blocks = re.findall(r'<a class="result__snippet[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
        if not blocks:
            # Alternate pattern
            links = re.findall(r'<a class="result__url"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
            snippets = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', html)
            for i in range(min(len(links), len(snippets), max_results)):
                url_raw = links[i][0]
                url_clean = urllib.parse.unquote(url_raw.split("uddg=")[-1].split("&")[0]) if "uddg=" in url_raw else url_raw
                snip = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                results.append(f"{i+1}. [Источник: {url_clean}]\n   {snip}")
        else:
            for idx, (url_raw, snippet_html) in enumerate(blocks[:max_results]):
                url_clean = urllib.parse.unquote(url_raw.split("uddg=")[-1].split("&")[0]) if "uddg=" in url_raw else url_raw
                snip = re.sub(r'<[^>]+>', '', snippet_html).strip()
                results.append(f"{idx+1}. [Источник: {url_clean}]\n   {snip}")
                
        if results:
            return f"🔍 Результаты поиска по запросу «{clean_q}»:\n\n" + "\n\n".join(results)
        
        # Fallback to direct summary request
        return f"🔍 Поиск по «{clean_q}» выполнен, но прямые сниппеты не найдены (попробуйте уточнить запрос)."
    except Exception as e:
        return f"⚠️ Ошибка веб-поиска: {e}"

def tool_scrape_webpage(url: str, max_chars: int = 5000) -> str:
    """Скачивает и извлекает читаемый текстовый контент веб-страницы."""
    target_url = url.strip()
    if not target_url.startswith("http"):
        target_url = f"https://{target_url}"
        
    req = urllib.request.Request(
        target_url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw_html = response.read().decode("utf-8", errors="ignore")
            
        # Clean HTML: remove scripts, styles, comments
        text = re.sub(r'<script[\s\S]*?</script>', '', raw_html, flags=re.I)
        text = re.sub(r'<style[\s\S]*?</style>', '', text, flags=re.I)
        text = re.sub(r'<!--[\s\S]*?-->', '', text)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Title extraction
        title_match = re.search(r'<title[^>]*>(.*?)</title>', raw_html, re.I)
        title = title_match.group(1).strip() if title_match else "Без заголовка"
        
        preview = text[:max_chars]
        return f"📄 Содержимое страницы: «{title}» ({target_url})\n\n{preview}\n\n...(всего {len(text)} симв.)"
    except Exception as e:
        return f"⚠️ Ошибка чтения страницы {target_url}: {e}"

def tool_osint_lookup(target: str, lookup_type: str = "domain") -> str:
    """Выполняет OSINT-разведку домена, IP-адреса или веб-сервиса (DNS, заголовки, технологии)."""
    clean_target = target.strip().replace("https://", "").replace("http://", "").split("/")[0]
    out = [f"🛡️ [OSINT ОТЧЕТ] Цель: {clean_target} | Время: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    
    # 1. DNS Resolution
    try:
        ip = socket.gethostbyname(clean_target)
        out.append(f"• IP-адрес: {ip}")
    except Exception as e:
        out.append(f"• DNS-резолв: Ошибка ({e})")
        ip = None
        
    # 2. HTTP Headers & Server Detection
    try:
        req = urllib.request.Request(f"https://{clean_target}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = dict(resp.headers)
            out.append(f"• HTTP Статус: {resp.status}")
            out.append(f"• Веб-сервер: {headers.get('Server', 'Скрыт')}")
            out.append(f"• Content-Type: {headers.get('Content-Type', 'N/A')}")
            if 'X-Powered-By' in headers:
                out.append(f"• Фреймворк (X-Powered-By): {headers.get('X-Powered-By')}")
            if 'Strict-Transport-Security' in headers:
                out.append("• Защита HTTPS (HSTS): Включена")
    except Exception as e:
        out.append(f"• Проверка HTTPS: {e}")
        
    return "\n".join(out)

# ==============================================================================
# 2. 🐙 GIT OPERATIONS, TERMINAL & CODE EXECUTION
# ==============================================================================

def tool_git_clone(repo_url: str, target_dir_name: str = "") -> str:
    """Клонирует Git/GitHub репозиторий в папку projects/ на HomeServer."""
    url = repo_url.strip()
    if not url.startswith("http"):
        url = f"https://github.com/{url}" if "/" in url else url
        
    repo_name = target_dir_name or url.rstrip("/").split("/")[-1].replace(".git", "")
    dest_path = PROJECTS_DIR / repo_name
    
    if dest_path.exists():
        return f"📁 Репозиторий уже существует в {dest_path}. Для обновления используйте git pull."
        
    print(f"🐙 [GIT] Клонирование {url} в {dest_path}...")
    try:
        res = subprocess.run(
            ["git", "clone", url, str(dest_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120
        )
        if res.returncode == 0:
            files = [f.name for f in dest_path.glob("*") if not f.name.startswith(".")]
            return f"✅ Репозиторий «{repo_name}» успешно склонирован в {dest_path}!\nФайлы: {', '.join(files[:20])}"
        return f"⚠️ Ошибка git clone: {res.stderr}"
    except Exception as e:
        return f"⚠️ Сбой клонирования: {e}"

def tool_run_terminal_command(command: str, cwd: str = "", timeout_sec: int = 60) -> str:
    """Безопасно выполняет консольную команду в системе и возвращает результат."""
    cmd = command.strip()
    
    # Block dangerous system-destroying commands
    blocked_patterns = [r"format\s+[a-z]:", r"rmdir\s+/s\s+/q\s+c:\\", r"del\s+/f\s+/s\s+/q\s+c:\\windows", r"powershell.*remove-item\s+c:\\\s+-recurse"]
    for bp in blocked_patterns:
        if re.search(bp, cmd, re.I):
            return "🚫 Команда заблокирована политикой безопасности HomeServer (опасная системная операция)."

    work_dir = Path(cwd) if cwd else BASE_DIR
    if not work_dir.exists():
        work_dir = BASE_DIR
        
    try:
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec
        )
        out = res.stdout.strip()
        err = res.stderr.strip()
        
        output_parts = []
        if out:
            output_parts.append(f"STDOUT:\n{out[:3000]}")
        if err:
            output_parts.append(f"STDERR:\n{err[:1500]}")
        if not output_parts:
            output_parts.append("(Команда завершилась без вывода в консоль)")
            
        return f"💻 [ВЫПОЛНЕНО: код {res.returncode}]\n" + "\n\n".join(output_parts)
    except subprocess.TimeoutExpired:
        return f"⏱️ Команда превысила тайм-аут ({timeout_sec} сек) и была остановлена."
    except Exception as e:
        return f"⚠️ Ошибка выполнения команды: {e}"

def tool_run_python_script(script_path: str, args: list = None) -> str:
    """Запускает Python-скрипт в виртуальном окружении HomeServer (venv)."""
    p = Path(script_path)
    if not p.is_absolute():
        p = BASE_DIR / script_path
    if not p.exists():
        return f"Файл скрипта '{script_path}' не найден."
        
    cmd = [str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable, str(p)]
    if args:
        cmd.extend([str(a) for a in args])
        
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        return f"🐍 [PYTHON СКРИПТ: {p.name} (код {res.returncode})]\n\n{res.stdout[:3000]}\n{res.stderr[:1000]}"
    except Exception as e:
        return f"⚠️ Ошибка запуска Python скрипта: {e}"

def tool_write_code_file(file_path: str, content: str) -> str:
    """Создает или обновляет файл с кодом/текстом на сервере."""
    p = Path(file_path)
    if not p.is_absolute():
        p = BASE_DIR / file_path
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ Файл успешно сохранен: {p.relative_to(BASE_DIR) if BASE_DIR in p.parents else p} ({len(content)} симв.)"
    except Exception as e:
        return f"⚠️ Ошибка записи файла: {e}"

# ==============================================================================
# 3. 🎯 LEAD GENERATION & CONTACT EXTRACTION
# ==============================================================================

def tool_leadgen_extract_contacts(url_or_text: str, source_name: str = "") -> str:
    """Извлекает контакты (Email, телефоны, Telegram, VK, соцсети) из веб-страницы или текста."""
    raw_text = url_or_text.strip()
    page_title = source_name or "Лиды"
    
    # If URL is passed, scrape it first
    if raw_text.startswith("http://") or raw_text.startswith("https://"):
        try:
            req = urllib.request.Request(raw_text, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                page_title = raw_text
                raw_text = html
        except Exception as e:
            return f"⚠️ Не удалось загрузить сайт для сбора лидов: {e}"
            
    # Extraction regexes
    emails = list(set(re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', raw_text)))
    # Filter out dummy/file extension emails
    emails = [e for e in emails if not e.endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp', '.js', '.css'))]
    
    phones = list(set(re.findall(r'(?:\+7|8)[\s\-]?(?:\(?\d{3}\)?[\s\-]?)?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', raw_text)))
    telegrams = list(set(re.findall(r'(?:t\.me\/|@)([a-zA-Z0-9_]{4,32})', raw_text)))
    vks = list(set(re.findall(r'vk\.com\/([a-zA-Z0-9_.]{3,32})', raw_text)))
    
    lead_entry = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": page_title,
        "emails": emails,
        "phones": phones,
        "telegram": telegrams,
        "vk": vks
    }
    
    # Save to leads database (JSON)
    leads_file = LEADS_DIR / "leads_database.json"
    db = []
    if leads_file.exists():
        try:
            db = json.loads(leads_file.read_text(encoding="utf-8"))
        except Exception:
            db = []
    db.append(lead_entry)
    leads_file.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    
    report = [
        f"🎯 [LEADGEN ОТЧЕТ] Источник: {page_title}",
        f"• Найдено Email: {len(emails)} ({', '.join(emails) if emails else 'нет'})",
        f"• Найдено Телефонов: {len(phones)} ({', '.join(phones) if phones else 'нет'})",
        f"• Telegram: {', '.join(['@' + t for t in telegrams]) if telegrams else 'нет'}",
        f"• VK: {', '.join(vks) if vks else 'нет'}",
        f"📁 Данные сохранены в data/leads/leads_database.json"
    ]
    return "\n".join(report)

def tool_export_leads_csv(filename: str = "leads_export.csv") -> str:
    """Экспортирует всю базу собранных лидов в CSV-таблицу."""
    leads_file = LEADS_DIR / "leads_database.json"
    if not leads_file.exists():
        return "База лидов пуста. Сначала выполните поиск через tool_leadgen_extract_contacts."
        
    try:
        db = json.loads(leads_file.read_text(encoding="utf-8"))
        csv_file = LEADS_DIR / filename
        with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Дата", "Источник", "Emails", "Телефоны", "Telegram", "VK"])
            for row in db:
                writer.writerow([
                    row.get("timestamp", ""),
                    row.get("source", ""),
                    "; ".join(row.get("emails", [])),
                    "; ".join(row.get("phones", [])),
                    "; ".join(row.get("telegram", [])),
                    "; ".join(row.get("vk", []))
                ])
        return f"✅ Экспорт завершен: {csv_file} (всего записей: {len(db)})"
    except Exception as e:
        return f"⚠️ Ошибка экспорта CSV: {e}"

# ==============================================================================
# 4. 🧠 DEEP RESEARCH & REPORT SYNTHESIS
# ==============================================================================

def tool_deep_research(topic: str, depth: int = 3) -> str:
    """Проводит глубокое аналитическое исследование темы в интернете и сохраняет отчет в archive/research/."""
    from core.chat_agent import query_gemini_raw, get_system_prompt
    
    clean_topic = topic.strip()
    print(f"🧠 [DEEP RESEARCH] Старт исследования: «{clean_topic}»...")
    
    # 1. Search top sources
    search_queries = [
        clean_topic,
        f"{clean_topic} обзор ключевые технологии и тренды",
        f"{clean_topic} лучшие практики и примеры"
    ]
    
    all_findings = []
    for q in search_queries[:depth]:
        search_res = tool_web_search(q, max_results=4)
        all_findings.append(search_res)
        time.sleep(1)
        
    combined_raw = "\n\n".join(all_findings)
    
    # 2. Synthesize with Cloud Gemini Flash
    prompt = f"""
Ты — ведущий аналитик и AI-исследователь. На основе собранных сырых данных проведи детальный синтез и напиши исчерпывающий аналитический отчет по теме: «{clean_topic}».

СЫРЫЕ ДАННЫЕ ИЗ СЕТИ:
{combined_raw}

ТРЕБОВАНИЯ К ОТЧЕТУ:
1. Заголовок первого уровня с темой.
2. Введение и актуальность.
3. Ключевые архитектурные или практические концепции.
4. Сравнительный анализ / ключевые инсайты.
5. Практические выводы и дорожная карта применения.
6. Список источников.
Пиши структурированно, профессионально, с таблицами и Markdown форматированием.
"""
    report_md = query_gemini_raw(get_system_prompt(), prompt)
    if not report_md:
        report_md = f"# Исследование: {clean_topic}\n\nСырые данные:\n\n{combined_raw}"
        
    # 3. Save report to archive/research/
    slug = re.sub(r'[^a-zA-Zа-яА-Я0-9_-]', '_', clean_topic)[:40]
    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    report_filename = f"RESEARCH_{slug}_{date_str}.md"
    report_path = RESEARCH_DIR / report_filename
    
    report_path.write_text(report_md, encoding="utf-8")
    return f"📑 [DEEP RESEARCH ЗАВЕРШЕНО]\nТема: «{clean_topic}»\nГотовый отчет сохранен: archive/research/{report_filename} ({len(report_md)} симв.)\n\nПревью:\n{report_md[:1200]}..."

# ==============================================================================
# TOOL REGISTRY EXPORT
# ==============================================================================




# ==============================================================================
# 📦 FILE PACKAGING, DOWNLOADS & CHAT DELIVERY (White-List Rescue Suite)
# ==============================================================================

def tool_download_file(url: str, output_name: str = "") -> str:
    """Скачивает файл или программу из интернета по прямой ссылке и сохраняет в INBOX."""
    clean_url = url.strip()
    if not clean_url:
        return "Ошибка: не указан URL для скачивания."
    
    if not output_name:
        output_name = clean_url.split("?")[0].rstrip("/").split("/")[-1]
    if not output_name:
        output_name = f"download_{int(time.time())}.bin"
        
    dest = (BASE_DIR / "inbox" / output_name)
    BASE_DIR.joinpath("inbox").mkdir(parents=True, exist_ok=True)
    
    req = urllib.request.Request(clean_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp, open(dest, "wb") as out_f:
            out_f.write(resp.read())
        size_kb = dest.stat().st_size / 1024
        return f"✅ Файл '{output_name}' успешно скачан ({size_kb:.1f} КБ) и сохранен в INBOX.\nДля отправки в чат укажите [SEND_FILE:{dest}]."
    except Exception as e:
        return f"❌ Ошибка скачивания '{output_name}': {e}"

def tool_create_zip_archive(source_path: str, zip_name: str = "") -> str:
    """Упаковывает файл или целую папку в надежный чистый ZIP-архив без битых кодировок."""
    import zipfile
    src = Path(source_path)
    if not src.exists():
        return f"Ошибка: путь '{source_path}' не найден."
        
    if not zip_name:
        zip_name = f"{src.stem}.zip"
    if not zip_name.endswith(".zip"):
        zip_name += ".zip"
        
    out_zip = BASE_DIR / "inbox" / zip_name
    BASE_DIR.joinpath("inbox").mkdir(parents=True, exist_ok=True)
    
    try:
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            if src.is_file():
                z.write(src, src.name)
            else:
                for root, _, files in os.walk(src):
                    for file in files:
                        p = Path(root) / file
                        arcname = p.relative_to(src)
                        z.write(p, arcname)
                        
        size_mb = out_zip.stat().st_size / (1024 * 1024)
        return f"✅ ZIP-архив '{zip_name}' создан ({size_mb:.2f} МБ) в INBOX.\nДля отправки в чат укажите [SEND_FILE:{out_zip}]."
    except Exception as e:
        return f"❌ Ошибка создания ZIP: {e}"

def tool_send_file_to_user(file_path: str) -> str:
    """Формирует команду прямой отправки файла или драйвера в чат ВКонтакте / MAX."""
    p = Path(file_path)
    if not p.exists():
        # check desktop or inbox
        dt_p = Path("C:/Users/user/Desktop") / p.name
        ib_p = BASE_DIR / "inbox" / p.name
        if dt_p.exists():
            p = dt_p
        elif ib_p.exists():
            p = ib_p
        else:
            return f"Ошибка: файл '{file_path}' не существует на сервере."
            
    return f"Готовлю отправку файла в чат...\n[SEND_FILE:{p}]"


# ==============================================================================
# 🧩 DYNAMIC SKILLS & AUTO-EXTENSIBILITY (Skills Store & Auto-Installer)
# ==============================================================================

def tool_search_skills(query: str) -> str:
    """Ищет доступные навыки и расширения в каталоге скиллов по теме задачи."""
    from core.skill_manager import search_skills
    skills = search_skills(query)
    if not skills:
        return f"По запросу '{query}' скиллов в каталоге не найдено."
    res = [f"• [{s['id']}] {s['name']}: {s['description']}" for s in skills]
    return "ДОСТУПНЫЕ НАВЫКИ В КАТАЛОГЕ:\n" + "\n".join(res)

def tool_install_skill(skill_id_or_url: str) -> str:
    """Автономно устанавливает и активирует новый навык (из каталога или GitHub репозитория)."""
    from core.skill_manager import install_skill
    return install_skill(skill_id_or_url)

def tool_list_installed_skills() -> str:
    """Возвращает список всех активных и установленных навыков на сервере."""
    from core.skill_manager import list_installed_skills
    skills = list_installed_skills()
    if not skills:
        return "Пока нет установленных навыков."
    res = [f"• {s['name']} (ID: {s['id']})" for s in skills]
    return "АКТИВНЫЕ НАВЫКИ:\n" + "\n".join(res)


# ------------------------------------------------------------------------------
# 📓 NOTEBOOKLM & CLOUD CODE TOOLS
# ------------------------------------------------------------------------------

def tool_notebooklm_synthesize(source_text_or_path: str, format_type: str = "briefing") -> str:
    """
    Генерирует структурированные артефакты знаний в стиле Google NotebookLM:
    format_type: 'briefing' (аналитическая записка), 'faq' (вопросы и ответы), 
                 'study_guide' (учебное руководство), 'podcast_script' (сценарий аудио-подкаста).
    """
    from core.chat_agent import query_llm_text
    
    # Read if path
    p = Path(source_text_or_path.strip())
    content = ""
    if p.exists() and p.is_file():
        try:
            content = p.read_text(encoding="utf-8", errors="replace")[:12000]
        except Exception:
            content = f"Файл {p.name}"
    else:
        content = source_text_or_path[:12000]

    prompts = {
        "briefing": f"Ты — NotebookLM Research Assistant. Подготовь подробную аналитическую записку (Briefing Doc) по материалам:\n{content}\n\nСтруктура: 1. Ключевая суть 2. Важнейшие факты и данные 3. Стратегические выводы 4. Практические шаги.",
        "faq": f"Ты — NotebookLM Research Assistant. Сформируй исчерпывающий список часто задаваемых вопросов и подробных ответов (FAQ) на основе материалов:\n{content}",
        "study_guide": f"Ты — NotebookLM Учебный Ментор. Составь пошаговое учебное руководство (Study Guide) с контрольными вопросами и глоссарием ключевых терминов по материалам:\n{content}",
        "podcast_script": f"Ты — автор подкаста в стиле NotebookLM Audio Overview. Напиши живой, увлекательный сценарий диалога двух ведущих (Алексей и Елена), обсуждающих тему:\n{content}\n\nДиалог должен быть неформальным, с яркими аналогиями, юмором и глубоким раскрытием темы."
    }

    selected_prompt = prompts.get(format_type, prompts["briefing"])
    sys_inst = "Ты — профессиональный исследовательский интеллект NotebookLM. Пиши структурированно, содержательно и на чистом русском языке."
    
    try:
        report = query_llm_text(sys_inst, selected_prompt)
        # Save output to documents
        out_dir = BASE_DIR / "data" / "documents"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"NotebookLM_{format_type}_{int(time.time())}.md"
        out_file.write_text(report, encoding="utf-8")
        return f"✅ Анализ NotebookLM [{format_type}] сформирован и сохранен в {out_file.name}:\n\n{report[:1000]}...\n\n[Полный документ сохранен: {out_file}]"
    except Exception as e:
        return f"Ошибка синтеза NotebookLM: {e}"

def tool_cloud_code_runner(code_str: str, filename: str = "cloud_script.py") -> str:
    """
    Создает и безопасно запускает Python/Jupyter скрипт анализа данных в виртуальном окружении HomeServer.
    """
    import subprocess
    code_dir = BASE_DIR / "data" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    target_file = code_dir / filename
    
    try:
        target_file.write_text(code_str, encoding="utf-8")
        venv_py = BASE_DIR / "venv" / "Scripts" / "python.exe"
        if not venv_py.exists():
            venv_py = Path(sys.executable)
            
        res = subprocess.run(
            [str(venv_py), str(target_file)],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=str(BASE_DIR)
        )
        
        output = res.stdout if res.stdout else ""
        if res.stderr:
            output += f"\n[STDERR]:\n{res.stderr}"
            
        return f"🚀 Cloud Code запущен ({filename}) [Exit Code: {res.returncode}]:\n{output[:1500]}"
    except Exception as e:
        return f"Ошибка запуска Cloud Code: {e}"

ALL_AGENT_TOOLS = {
    "tool_search_skills": tool_search_skills,
    "tool_install_skill": tool_install_skill,
    "tool_list_installed_skills": tool_list_installed_skills,
    "tool_download_file": tool_download_file,
    "tool_create_zip_archive": tool_create_zip_archive,
    "tool_notebooklm_synthesize": tool_notebooklm_synthesize,
    "tool_cloud_code_runner": tool_cloud_code_runner,
    "tool_send_file_to_user": tool_send_file_to_user,
    "tool_web_search": tool_web_search,
    "tool_scrape_webpage": tool_scrape_webpage,
    "tool_osint_lookup": tool_osint_lookup,
    "tool_git_clone": tool_git_clone,
    "tool_run_terminal_command": tool_run_terminal_command,
    "tool_run_python_script": tool_run_python_script,
    "tool_write_code_file": tool_write_code_file,
    "tool_leadgen_extract_contacts": tool_leadgen_extract_contacts,
    "tool_export_leads_csv": tool_export_leads_csv,
    "tool_deep_research": tool_deep_research
}
