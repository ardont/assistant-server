# -*- coding: utf-8 -*-
"""
HomeServer Web Hub & Control Panel
Lightweight HTTP Server for remote upload, live status, and AI proposal review.
"""
import os
import sys
import json
import time
import socket
import cgi
import threading
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.system_status import get_system_metrics
from core.notifier import notify_info, send_push
from tasks.file_ai_organizer import (
    get_all_proposals,
    apply_proposal,
    approve_all_pending,
    reject_proposal,
    scan_and_process_inbox,
    SERVER_INBOX,
    DATA_DIR
)
from core.auth_manager import (
    list_all_users,
    create_new_user,
    update_user_permissions,
    delete_user,
    bind_max_id_to_user,
    bind_vk_id_to_user,
    unbind_max_id_from_user,
    unbind_vk_id_from_user
)
from core.token_tracker import load_token_stats, set_user_quota, reset_user_tokens, remove_all_limits

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config", ".env"))
if os.path.exists(CONFIG_PATH):
    load_dotenv(CONFIG_PATH)

PORT = int(os.getenv("WEB_PORT", "8000"))
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "homeserver_my_secret_topic_123")

def get_server_ips():
    try:
        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)[2]
        return hostname, ips
    except Exception:
        return "Unknown", ["127.0.0.1"]

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class HomeServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ==================== GET ====================
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.serve_dashboard()
        elif self.path == "/api/status":
            hostname, ips = get_server_ips()
            metrics = get_system_metrics()
            self.send_json({
                "hostname": hostname,
                "ips": ips,
                "metrics": metrics,
                "ntfy_topic": NTFY_TOPIC
            })
        elif self.path == "/api/proposals":
            proposals = get_all_proposals()
            self.send_json(proposals)
        elif self.path == "/api/users":
            users = list_all_users()
            self.send_json(users)
        elif self.path == "/api/token_stats":
            stats = load_token_stats()
            users_stats = []
            for username, data in stats.get("users", {}).items():
                users_stats.append({
                    "username": username,
                    "total_tokens": data.get("total_tokens", 0),
                    "prompt_tokens": data.get("prompt_tokens", 0),
                    "completion_tokens": data.get("completion_tokens", 0),
                    "requests_count": data.get("requests_count", 0),
                    "quota": data.get("token_quota", 50000),
                    "models": list(data.get("models_usage", {}).keys())
                })
            self.send_json(users_stats)
        elif self.path == "/calendar.ics":
            self.serve_calendar_ics()
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    # ==================== POST ====================
    def do_POST(self):
        if self.path == "/api/upload":
            self.handle_file_upload()
        elif self.path == "/api/approve":
            self.handle_approve()
        elif self.path == "/api/approve_all":
            count = approve_all_pending()
            self.send_json({"success": True, "count": count})
        elif self.path == "/api/reject":
            self.handle_reject()
        elif self.path == "/api/scan":
            count = scan_and_process_inbox(auto_apply=False)
            self.send_json({"success": True, "new_files": count})
        elif self.path == "/api/test_push":
            ok = send_push("🟢 Тест связи", "Уведомление успешно доставлено на устройство!", priority="default", tags="bell,laptop")
            self.send_json({"success": ok})
        elif self.path == "/api/register":
            self.handle_register()
        elif self.path == "/api/update_quota":
            self.handle_update_quota()
        elif self.path == "/api/reset_tokens":
            self.handle_reset_tokens()
        elif self.path == "/api/admin/max/bind":
            self.handle_bind_max()
        elif self.path == "/api/admin/vk/bind":
            self.handle_bind_vk()
        elif self.path == "/api/admin/max/config":
            self.handle_save_max_token()
        else:
            self.send_response(404)
            self.end_headers()

    # ==================== Обработчики ====================
    def handle_file_upload(self):
        try:
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                content_length = int(self.headers.get("Content-Length", 0))
                filename = self.headers.get("X-File-Name", f"upload_{int(time.time())}.dat")
                data = self.rfile.read(content_length)
                target_file = SERVER_INBOX / filename
                with open(target_file, "wb") as f:
                    f.write(data)
                threading.Thread(target=scan_and_process_inbox, kwargs={"auto_apply": False}).start()
                self.send_json({"success": True, "file": filename})
                return

            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers["Content-Type"],
                }
            )

            if "file" in form:
                fileitem = form["file"]
                if fileitem.filename:
                    filename = os.path.basename(fileitem.filename)
                    target_file = SERVER_INBOX / filename
                    with open(target_file, "wb") as f:
                        f.write(fileitem.file.read())
                    threading.Thread(target=scan_and_process_inbox, kwargs={"auto_apply": False}).start()
                    self.send_json({"success": True, "file": filename})
                    return

            self.send_json({"success": False, "error": "No file uploaded"}, 400)
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_approve(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            prop_id = body.get("id")
            dest = body.get("destination")
            ok = apply_proposal(prop_id, dest)
            self.send_json({"success": ok})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_reject(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            prop_id = body.get("id")
            ok = reject_proposal(prop_id)
            self.send_json({"success": ok})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_register(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            username = body.get("username", "").strip()
            password = body.get("password", "").strip()
            display_name = body.get("display_name", "").strip()
            role = body.get("role", "user")
            permissions = body.get("permissions", {})
            ok, msg = create_new_user(username, password, role, display_name, permissions)
            self.send_json({"success": ok, "message": msg})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_update_quota(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            username = body.get("username")
            quota = body.get("quota")
            if quota is None:
                quota = -1  # бесконечность
            ok = set_user_quota(username, quota)
            self.send_json({"success": ok})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_reset_tokens(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            username = body.get("username")
            ok = reset_user_tokens(username)
            self.send_json({"success": ok})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_bind_max(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            username = body.get("username", "").strip()
            max_id = str(body.get("max_id", "")).strip()
            ok, msg = bind_max_id_to_user(username, max_id)
            self.send_json({"success": ok, "message": msg})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_bind_vk(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            username = body.get("username", "").strip()
            vk_id = str(body.get("vk_id", "")).strip()
            ok, msg = bind_vk_id_to_user(username, vk_id)
            self.send_json({"success": ok, "message": msg})
        except Exception as e:
            self.send_json({"success": False, "error": str(e)}, 500)

    def handle_save_max_token(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            token = body.get("max_bot_token", "").strip()
            env_path = Path("C:/HomeServer/config/.env")
            lines = []
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()
            updated = False
            new_lines = []
            for line in lines:
                if line.startswith("MAX_BOT_TOKEN="):
                    new_lines.append(f"MAX_BOT_TOKEN={token}")
                    updated = True
                else:
                    new_lines.append(line)
            if not updated:
                new_lines.append(f"MAX_BOT_TOKEN={token}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            self.send_json({"status": "ok", "message": "Токен MAX Bot сохранён в .env. Перезапустите сервер для применения."})
        except Exception as e:
            self.send_json({"status": "error", "message": str(e)}, 500)

    def serve_calendar_ics(self):
        now = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//HomeServer//Automation Center//RU
CALSCALE:GREGORIAN
METHOD:PUBLISH
X-WR-CALNAME:HomeServer Maintenance & Heartbeat
X-WR-TIMEZONE:Europe/Moscow
BEGIN:VEVENT
UID:homeserver-heartbeat-daily@homeserver
DTSTAMP:{now}
DTSTART:{now}
RRULE:FREQ=DAILY;INTERVAL=1
SUMMARY:🟢 HomeServer Daily Status Check
DESCRIPTION:Ежедневная проверка статуса сервера HomeServer и свободного места на диске.
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:homeserver-inbox-review@homeserver
DTSTAMP:{now}
DTSTART:{now}
RRULE:FREQ=HOURLY;INTERVAL=6
SUMMARY:📥 HomeServer INBOX Review
DESCRIPTION:Проверка разобранных файлов искусственным интеллектом Gemini.
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""
        body = ics_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="homeserver_schedule.ics"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_dashboard(self):
        html_template = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HomeServer 24/7 AI Hub</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0f172a;
            --bg-card: rgba(30, 41, 59, 0.7);
            --bg-card-hover: rgba(51, 65, 85, 0.8);
            --border: rgba(255, 255, 255, 0.08);
            --accent: #38bdf8;
            --accent-glow: rgba(56, 189, 248, 0.25);
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-base);
            background-image: radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 50%),
                              radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.12) 0px, transparent 50%);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 24px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }
        .logo-group {
            display: flex;
            align-items: center;
            gap: 14px;
        }
        .status-dot {
            width: 14px;
            height: 14px;
            background: var(--success);
            border-radius: 50%;
            box-shadow: 0 0 12px var(--success);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.15); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }
        h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.5px; }
        .header-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .btn {
            background: var(--bg-card);
            color: var(--text-primary);
            border: 1px solid var(--border);
            padding: 9px 16px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
        }
        .btn:hover {
            background: var(--bg-card-hover);
            border-color: var(--accent);
            transform: translateY(-1px);
        }
        .btn-primary {
            background: linear-gradient(135deg, #0284c7, #0ea5e9);
            border: none;
            box-shadow: 0 4px 14px var(--accent-glow);
        }
        .btn-primary:hover {
            background: linear-gradient(135deg, #0369a1, #0284c7);
        }
        .btn-success {
            background: rgba(52, 211, 153, 0.15);
            color: var(--success);
            border: 1px solid rgba(52, 211, 153, 0.3);
        }
        .btn-success:hover { background: rgba(52, 211, 153, 0.25); }
        .btn-danger {
            background: rgba(248, 113, 113, 0.15);
            color: var(--danger);
            border: 1px solid rgba(248, 113, 113, 0.3);
        }
        .btn-danger:hover { background: rgba(248, 113, 113, 0.25); }

        /* Tabs */
        .tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 24px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 4px;
        }
        .tab {
            padding: 10px 20px;
            border-radius: 8px 8px 0 0;
            cursor: pointer;
            font-weight: 500;
            color: var(--text-secondary);
            transition: all 0.2s;
            border: 1px solid transparent;
            border-bottom: none;
        }
        .tab:hover {
            background: var(--bg-card);
            color: var(--text-primary);
        }
        .tab.active {
            background: var(--bg-card);
            color: var(--text-primary);
            border-color: var(--border);
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 28px;
        }
        .card {
            background: var(--bg-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 20px;
            position: relative;
            overflow: hidden;
        }
        .card h2 {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 14px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .stat-val {
            font-size: 26px;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 4px;
        }
        .stat-sub { font-size: 13px; color: var(--text-secondary); }
        .progress-bar {
            height: 6px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 3px;
            margin-top: 10px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: var(--accent);
            border-radius: 3px;
            transition: width 0.4s ease;
        }

        .upload-zone {
            border: 2px dashed rgba(56, 189, 248, 0.4);
            border-radius: 14px;
            padding: 32px 20px;
            text-align: center;
            background: rgba(15, 23, 42, 0.5);
            cursor: pointer;
            transition: all 0.2s ease;
            margin-bottom: 28px;
        }
        .upload-zone:hover, .upload-zone.dragover {
            border-color: var(--accent);
            background: rgba(56, 189, 248, 0.08);
        }
        .upload-icon { font-size: 38px; margin-bottom: 10px; }
        .upload-text { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
        .upload-hint { font-size: 13px; color: var(--text-secondary); }

        .section-title {
            font-size: 19px;
            font-weight: 600;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .proposal-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            transition: border-color 0.2s ease;
        }
        .proposal-card:hover { border-color: rgba(56, 189, 248, 0.3); }
        .proposal-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            flex-wrap: wrap;
        }
        .file-title {
            font-size: 16px;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
            color: var(--accent);
        }
        .badge {
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            text-transform: uppercase;
        }
        .badge-documents { background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
        .badge-spreadsheets { background: rgba(52, 211, 153, 0.15); color: #34d399; }
        .badge-code { background: rgba(168, 85, 247, 0.15); color: #c084fc; }
        .badge-media { background: rgba(244, 114, 182, 0.15); color: #f472b6; }
        .badge-archives { background: rgba(251, 191, 36, 0.15); color: #fbbf24; }
        .badge-other { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }

        .ai-summary {
            font-size: 14px;
            line-height: 1.5;
            color: #cbd5e1;
            background: rgba(15, 23, 42, 0.6);
            padding: 12px 14px;
            border-radius: 8px;
            border-left: 3px solid var(--accent);
        }
        .path-box {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 13px;
            color: var(--text-secondary);
        }
        .path-input {
            flex: 1;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 7px 10px;
            border-radius: 6px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
        }
        .tags { display: flex; gap: 6px; flex-wrap: wrap; }
        .tag {
            font-size: 11px;
            background: rgba(255, 255, 255, 0.06);
            padding: 2px 8px;
            border-radius: 4px;
            color: var(--text-secondary);
        }
        .actions {
            display: flex;
            gap: 8px;
            justify-content: flex-end;
            margin-top: 4px;
        }
        .connect-guide {
            background: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 18px;
            margin-top: 24px;
            font-size: 13px;
            line-height: 1.6;
        }
        .connect-guide code {
            background: rgba(0, 0, 0, 0.4);
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--accent);
            font-family: 'JetBrains Mono', monospace;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            font-size: 14px;
        }
        th {
            text-align: left;
            padding: 10px 8px;
            color: var(--text-secondary);
            font-weight: 500;
            border-bottom: 1px solid var(--border);
        }
        td {
            padding: 10px 8px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .form-group {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            align-items: center;
            margin: 12px 0;
        }
        .form-group input, .form-group select {
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
        }
        .form-group label {
            color: var(--text-secondary);
            font-size: 13px;
        }
        .inline-check {
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .inline-check input[type="checkbox"] {
            width: 16px;
            height: 16px;
            accent-color: var(--accent);
        }
    </style>
</head>
<body>
<div class="container">
    <header>
        <div class="logo-group">
            <div class="status-dot"></div>
            <div>
                <h1>HomeServer 24/7 AI Hub</h1>
                <div style="font-size: 12px; color: var(--text-secondary);" id="host-sub">Подключение...</div>
            </div>
        </div>
        <div class="header-actions">
            <button class="btn" onclick="triggerScan()">🔄 Сканировать INBOX</button>
            <button class="btn" onclick="testPush()">🔔 Тест Push</button>
            <a href="/calendar.ics" class="btn">📅 Календарь (.ics)</a>
        </div>
    </header>

    <!-- Tabs -->
    <div class="tabs">
        <div class="tab active" data-tab="dashboard">📊 Дашборд</div>
        <div class="tab" data-tab="users">👥 Пользователи</div>
        <div class="tab" data-tab="tokens">📈 Токены</div>
        <div class="tab" data-tab="invites">🔑 Инвайты</div>
    </div>

    <!-- ===== TAB: DASHBOARD ===== -->
    <div id="tab-dashboard" class="tab-content active">
        <div class="grid">
            <div class="card">
                <h2>⚡ Процессор <span id="cpu-text">0%</span></h2>
                <div class="stat-val" id="cpu-val">--%</div>
                <div class="progress-bar"><div class="progress-fill" id="cpu-bar" style="width: 0%;"></div></div>
            </div>
            <div class="card">
                <h2>🧠 ОЗУ <span id="ram-text">-- / -- ГБ</span></h2>
                <div class="stat-val" id="ram-val">--%</div>
                <div class="progress-bar"><div class="progress-fill" id="ram-bar" style="width: 0%;"></div></div>
            </div>
            <div class="card">
                <h2>💾 Диск C: <span id="disk-text">-- ГБ свободно</span></h2>
                <div class="stat-val" id="disk-val">--%</div>
                <div class="progress-bar"><div class="progress-fill" id="disk-bar" style="width: 0%;"></div></div>
            </div>
            <div class="card">
                <h2>⏱️ Аптайм</h2>
                <div class="stat-val" id="uptime-val">-- ч</div>
                <div class="stat-sub" id="ip-info">IP: --</div>
            </div>
        </div>

        <div class="upload-zone" id="uploadZone" onclick="document.getElementById('fileInput').click()">
            <input type="file" id="fileInput" multiple style="display: none;" onchange="handleFiles(this.files)">
            <div class="upload-icon">📥</div>
            <div class="upload-text">Перетащите файлы сюда для отправки в INBOX</div>
            <div class="upload-hint">Или нажмите для выбора файлов с ноутбука/телефона • AI автоматически разберет их через 30 сек</div>
        </div>

        <div class="section-title">
            <span>🤖 Лист Согласования Файлов (Google Gemini 3.6 Flash)</span>
            <button class="btn btn-success" id="btnApproveAll" style="display: none;" onclick="approveAll()">✨ Принять все предложения</button>
        </div>
        <div id="proposalsList">
            <div class="card" style="text-align: center; color: var(--text-secondary);">Загрузка очереди входящих файлов...</div>
        </div>
    </div>

    <!-- ===== TAB: USERS ===== -->
    <div id="tab-users" class="tab-content">
        <h2 style="margin-bottom: 16px;">👥 Зарегистрированные пользователи</h2>
        <div id="usersTableWrap">
            <table>
                <thead>
                    <tr>
                        <th>Пользователь</th>
                        <th>Роль</th>
                        <th>Чат</th>
                        <th>Хранилище</th>
                        <th>Скрипты</th>
                        <th>Скиллы</th>
                        <th>Админ</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody id="usersTableBody">
                    <tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Загрузка...</td></tr>
                </tbody>
            </table>
        </div>

        <div class="card" style="margin-top: 24px;">
            <h3>➕ Зарегистрировать нового пользователя</h3>
            <div class="form-group">
                <label>Логин: <input type="text" id="regUsername" placeholder="alex"></label>
                <label>Пароль: <input type="password" id="regPassword" placeholder="пароль"></label>
                <label>Отображаемое имя: <input type="text" id="regDisplay" placeholder="Алексей"></label>
                <label>Роль:
                    <select id="regRole">
                        <option value="user">Пользователь</option>
                        <option value="admin">Администратор</option>
                    </select>
                </label>
            </div>
            <div class="form-group" style="flex-wrap: wrap;">
                <span style="color: var(--text-secondary); font-size:13px;">Права:</span>
                <label class="inline-check"><input type="checkbox" id="permChat" checked> Чат</label>
                <label class="inline-check"><input type="checkbox" id="permStorage"> Хранилище</label>
                <label class="inline-check"><input type="checkbox" id="permScripts"> Скрипты</label>
                <label class="inline-check"><input type="checkbox" id="permSkills"> Скиллы</label>
                <label class="inline-check"><input type="checkbox" id="permAdmin"> Админ</label>
                <button class="btn btn-primary" onclick="registerUser()">Создать пользователя</button>
            </div>
        </div>
    </div>

    <!-- ===== TAB: TOKENS ===== -->
    <div id="tab-tokens" class="tab-content">
        <h2 style="margin-bottom: 16px;">📊 Статистика использования токенов & квоты
            <button class="btn" onclick="loadTokenStats()" style="font-size:12px;">🔄 Обновить</button>
        </h2>
        <div id="tokenStatsWrap">
            <table>
                <thead>
                    <tr>
                        <th>Пользователь</th>
                        <th>Всего токенов</th>
                        <th>Prompt</th>
                        <th>Completion</th>
                        <th>Запросов</th>
                        <th>Текущий лимит</th>
                        <th>Модели</th>
                        <th>Действия</th>
                    </tr>
                </thead>
                <tbody id="tokenStatsBody">
                    <tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Загрузка...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- ===== TAB: INVITES ===== -->
    <div id="tab-invites" class="tab-content">
        <h2 style="margin-bottom: 16px;">🔑 VK Whitelist & Инвайт-коды</h2>
        
        <div class="card" style="margin-bottom: 20px;">
            <h3>📲 Привязка MAX ID к Пользователю</h3>
            <p style="color: var(--text-secondary); font-size: 13px; margin-bottom: 12px;">
                MAX user_id — это числовой ID пользователя в мессенджере MAX. 
                Чтобы узнать свой ID — напиши боту @se14050529_bot команду /status, он выведет твой MAX ID.
            </p>
            <div class="form-group">
                <label>Логин пользователя: 
                    <input type="text" id="bindMaxUsername" placeholder="ardont" value="ardont">
                </label>
                <label>MAX user_id (число): 
                    <input type="text" id="bindMaxId" placeholder="например: 418671076">
                </label>
                <button class="btn btn-primary" onclick="bindMaxId()">Привязать MAX ID</button>
            </div>
            <div id="bindMaxResult" style="margin-top: 8px; color: var(--text-secondary);"></div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <h3>📲 Привязка VK ID к Пользователю</h3>
            <div class="form-group">
                <label>Логин пользователя: 
                    <input type="text" id="bindVkUsername" placeholder="ardont" value="ardont">
                </label>
                <label>VK ID пользователя (число): 
                    <input type="text" id="bindVkId" placeholder="например: 12345678">
                </label>
                <button class="btn btn-primary" onclick="bindVkId()">Привязать VK ID</button>
            </div>
            <div id="bindVkResult" style="margin-top: 8px; color: var(--text-secondary);"></div>
        </div>

        <div class="card">
            <h3>⚙️ Настройка MAX Bot</h3>
            <div class="form-group">
                <label>MAX Bot Token (@MaxBotHub → MAX_BOT_TOKEN): 
                    <input type="text" id="maxBotToken" placeholder="вставьте токен..." style="width: 400px;">
                </label>
                <button class="btn btn-primary" onclick="saveMaxBotToken()">Сохранить токен</button>
            </div>
            <div id="maxBotResult" style="margin-top: 8px; color: var(--text-secondary);"></div>
        </div>
    </div>

    <!-- Quick Remote Connection Guide -->
    <div class="connect-guide">
        <h3 style="margin-bottom: 8px; font-size: 15px; color: var(--text-primary);">🌐 Как подключиться с другого компьютера / ноутбука:</h3>
        <p>1. <b>Сетевая папка Windows (SMB):</b> Нажмите <code>Win + R</code> на ноутбуке и введите: <code id="smb-link">\\\\192.168.50.108\\inbox</code></p>
        <p>2. <b>Прямой Web-доступ:</b> Откройте в любом браузере: <code id="web-link">http://192.168.50.108:8000</code> для загрузки и согласования.</p>
        <p>3. <b>Push-уведомления на телефон:</b> Установите приложение <b>ntfy</b> (iOS / Android) и подпишитесь на топик: <code id="ntfy-link">__NTFY_TOPIC__</code></p>
    </div>
</div>

<script>
    let currentProposals = [];

    // ========== TABS ==========
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', function() {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            document.getElementById('tab-' + this.dataset.tab).classList.add('active');
            if (this.dataset.tab === 'users') loadUsers();
            if (this.dataset.tab === 'tokens') loadTokenStats();
        });
    });

    // ========== STATUS ==========
    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            document.getElementById('host-sub').innerText = `${data.hostname} • ${data.ips.join(' / ')}`;
            document.getElementById('ip-info').innerText = `IP: ${data.ips.join(', ')}`;
            const m = data.metrics;
            document.getElementById('cpu-val').innerText = `${m.cpu_percent}%`;
            document.getElementById('cpu-bar').style.width = `${m.cpu_percent}%`;
            document.getElementById('ram-val').innerText = `${m.ram_percent}%`;
            document.getElementById('ram-bar').style.width = `${m.ram_percent}%`;
            document.getElementById('ram-text').innerText = `${m.ram_used_gb} / ${m.ram_total_gb} ГБ`;
            document.getElementById('disk-val').innerText = `${m.disk_percent}%`;
            document.getElementById('disk-bar').style.width = `${m.disk_percent}%`;
            document.getElementById('disk-text').innerText = `${m.disk_free_gb} ГБ свободно`;
            document.getElementById('uptime-val').innerText = `${m.uptime_hours} ч`;
            if (data.ips.length > 0) {
                const mainIp = data.ips[0];
                document.getElementById('smb-link').innerText = '\\\\' + mainIp + '\\inbox';
                document.getElementById('web-link').innerText = 'http://' + mainIp + ':' + (window.location.port || 8000);
            }
        } catch(e) { console.error('Status fetch error:', e); }
    }

    // ========== PROPOSALS ==========
    async function fetchProposals() {
        try {
            const res = await fetch('/api/proposals');
            const list = await res.json();
            currentProposals = list;
            renderProposals();
        } catch(e) { console.error('Proposals fetch error:', e); }
    }

    function renderProposals() {
        const container = document.getElementById('proposalsList');
        const pending = currentProposals.filter(p => p.status === 'pending');
        const btnApproveAll = document.getElementById('btnApproveAll');
        if (pending.length === 0) {
            btnApproveAll.style.display = 'none';
            container.innerHTML = `
                <div class="card" style="text-align: center; padding: 40px; color: var(--text-secondary);">
                    <div style="font-size: 32px; margin-bottom: 8px;">✨</div>
                    <div style="font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">Все входящие файлы согласованы!</div>
                    <div>Закиньте новые файлы в INBOX или перетащите их в зону загрузки выше.</div>
                </div>
            `;
            return;
        }
        btnApproveAll.style.display = 'inline-flex';
        container.innerHTML = pending.map((p, idx) => `
            <div class="proposal-card" id="card-${p.id}">
                <div class="proposal-header">
                    <div>
                        <span class="file-title">📄 ${p.file_name}</span>
                        <span style="font-size: 12px; color: var(--text-secondary); margin-left: 8px;">(${p.file_size_kb} КБ • ${p.detected_at})</span>
                    </div>
                    <span class="badge badge-${p.category}">${p.category}</span>
                </div>
                <div class="ai-summary"><b>🤖 Gemini AI резюме:</b> ${p.summary}</div>
                <div class="path-box">
                    <span>🎯 Куда:</span>
                    <input type="text" class="path-input" id="path-${p.id}" value="${p.suggested_destination}">
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div class="tags">${(p.tags || []).map(t => `<span class="tag">#${t}</span>`).join('')}</div>
                    <div class="actions">
                        <button class="btn" style="color: var(--danger); border-color: rgba(248, 113, 113, 0.3);" onclick="rejectProp('${p.id}')">🚫 Отклонить</button>
                        <button class="btn btn-primary" onclick="approveProp('${p.id}')">✅ Согласовать перемещение</button>
                    </div>
                </div>
            </div>
        `).join('');
    }

    async function approveProp(id) {
        const dest = document.getElementById(`path-${id}`).value;
        const res = await fetch('/api/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id, destination: dest })
        });
        const data = await res.json();
        if (data.success) fetchProposals();
        else alert('Ошибка перемещения файла.');
    }

    async function approveAll() {
        if (!confirm('Переместить все ожидающие файлы по предложенным AI путям?')) return;
        const res = await fetch('/api/approve_all', { method: 'POST' });
        const data = await res.json();
        alert(`Успешно перемещено файлов: ${data.count}`);
        fetchProposals();
    }

    async function rejectProp(id) {
        await fetch('/api/reject', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
        fetchProposals();
    }

    async function triggerScan() {
        const res = await fetch('/api/scan', { method: 'POST' });
        const data = await res.json();
        alert(`Сканирование завершено. Новых файлов: ${data.new_files}`);
        fetchProposals();
    }

    async function testPush() {
        const res = await fetch('/api/test_push', { method: 'POST' });
        const data = await res.json();
        alert(data.success ? 'Пуш-уведомление успешно отправлено!' : 'Ошибка отправки пуша.');
    }

    // ========== USERS ==========
    async function loadUsers() {
        try {
            const res = await fetch('/api/users');
            const users = await res.json();
            const tbody = document.getElementById('usersTableBody');
            if (!users.length) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Нет зарегистрированных пользователей</td></tr>`;
                return;
            }
            tbody.innerHTML = users.map(u => `
                <tr>
                    <td><b>${u.username}</b></td>
                    <td>${u.role}</td>
                    <td>${u.permissions?.can_chat ? '✅' : '❌'}</td>
                    <td>${u.permissions?.can_storage ? '✅' : '❌'}</td>
                    <td>${u.permissions?.can_execute_scripts ? '✅' : '❌'}</td>
                    <td>${u.permissions?.can_manage_skills ? '✅' : '❌'}</td>
                    <td>${u.permissions?.is_admin ? '✅' : '❌'}</td>
                    <td>
                        <button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="deleteUser('${u.username}')">Удалить</button>
                    </td>
                </tr>
            `).join('');
        } catch(e) { console.error('Users fetch error:', e); }
    }

    async function registerUser() {
        const username = document.getElementById('regUsername').value.trim();
        const password = document.getElementById('regPassword').value.trim();
        const display_name = document.getElementById('regDisplay').value.trim();
        const role = document.getElementById('regRole').value;
        const permissions = {
            can_chat: document.getElementById('permChat').checked,
            can_storage: document.getElementById('permStorage').checked,
            can_execute_scripts: document.getElementById('permScripts').checked,
            can_manage_skills: document.getElementById('permSkills').checked,
            is_admin: document.getElementById('permAdmin').checked
        };
        if (!username || !password) { alert('Логин и пароль обязательны'); return; }
        const res = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, display_name, role, permissions })
        });
        const data = await res.json();
        if (data.success) {
            alert(data.message);
            loadUsers();
            document.getElementById('regUsername').value = '';
            document.getElementById('regPassword').value = '';
            document.getElementById('regDisplay').value = '';
        } else {
            alert('Ошибка: ' + (data.message || data.error));
        }
    }

    async function deleteUser(username) {
        if (!confirm(`Удалить пользователя ${username}?`)) return;
        // Пока нет API для удаления, но можно добавить позже
        alert('Функция удаления будет добавлена в следующей версии');
    }

    // ========== TOKENS ==========
    async function loadTokenStats() {
        try {
            const res = await fetch('/api/token_stats');
            const stats = await res.json();
            const tbody = document.getElementById('tokenStatsBody');
            if (!stats.length) {
                tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-secondary);">Нет данных о токенах</td></tr>`;
                return;
            }
            tbody.innerHTML = stats.map(s => `
                <tr>
                    <td><b>${s.username}</b></td>
                    <td>${s.total_tokens}</td>
                    <td>${s.prompt_tokens}</td>
                    <td>${s.completion_tokens}</td>
                    <td>${s.requests_count}</td>
                    <td>${s.quota === -1 ? '∞' : s.quota}</td>
                    <td>${s.models.join(', ') || '—'}</td>
                    <td>
                        <button class="btn" style="padding:4px 8px; font-size:11px;" onclick="setQuota('${s.username}')">✏️ Квота</button>
                        <button class="btn btn-danger" style="padding:4px 8px; font-size:11px;" onclick="resetTokens('${s.username}')">🔄 Сброс</button>
                    </td>
                </tr>
            `).join('');
        } catch(e) { console.error('Token stats fetch error:', e); }
    }

    async function setQuota(username) {
        const newQuota = prompt(`Введите новую квоту для ${username} (число, -1 = ∞):`, '-1');
        if (newQuota === null) return;
        const quota = parseInt(newQuota);
        if (isNaN(quota)) { alert('Введите число'); return; }
        const res = await fetch('/api/update_quota', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, quota })
        });
        const data = await res.json();
        if (data.success) {
            alert('Квота обновлена');
            loadTokenStats();
        } else {
            alert('Ошибка: ' + (data.error || 'неизвестно'));
        }
    }

    async function resetTokens(username) {
        if (!confirm(`Сбросить статистику токенов для ${username}?`)) return;
        const res = await fetch('/api/reset_tokens', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username })
        });
        const data = await res.json();
        if (data.success) {
            alert('Статистика сброшена');
            loadTokenStats();
        } else {
            alert('Ошибка: ' + (data.error || 'неизвестно'));
        }
    }

    // ========== BIND MAX ID ==========
    async function bindMaxId() {
        const username = document.getElementById('bindMaxUsername').value.trim();
        const max_id = document.getElementById('bindMaxId').value.trim();
        if (!username || !max_id) {
            document.getElementById('bindMaxResult').innerHTML = '<span style="color: var(--danger);">Заполните оба поля.</span>';
            return;
        }
        const res = await fetch('/api/admin/max/bind', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, max_id })
        });
        const data = await res.json();
        const resultDiv = document.getElementById('bindMaxResult');
        if (data.success) {
            resultDiv.innerHTML = `<span style="color: var(--success);">✅ ${data.message}</span>`;
            loadUsers();
            loadTokenStats();
        } else {
            resultDiv.innerHTML = `<span style="color: var(--danger);">❌ ${data.message || data.error}</span>`;
        }
    }

    // ========== BIND VK ID ==========
    async function bindVkId() {
        const username = document.getElementById('bindVkUsername').value.trim();
        const vk_id = document.getElementById('bindVkId').value.trim();
        if (!username || !vk_id) {
            document.getElementById('bindVkResult').innerHTML = '<span style="color: var(--danger);">Заполните оба поля.</span>';
            return;
        }
        const res = await fetch('/api/admin/vk/bind', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, vk_id })
        });
        const data = await res.json();
        const resultDiv = document.getElementById('bindVkResult');
        if (data.success) {
            resultDiv.innerHTML = `<span style="color: var(--success);">✅ ${data.message}</span>`;
            loadUsers();
        } else {
            resultDiv.innerHTML = `<span style="color: var(--danger);">❌ ${data.message || data.error}</span>`;
        }
    }

    // ========== SAVE MAX BOT TOKEN ==========
    async function saveMaxBotToken() {
        const token = document.getElementById('maxBotToken').value.trim();
        if (!token) {
            document.getElementById('maxBotResult').innerHTML = '<span style="color: var(--danger);">Введите токен.</span>';
            return;
        }
        const res = await fetch('/api/admin/max/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_bot_token: token })
        });
        const data = await res.json();
        const resultDiv = document.getElementById('maxBotResult');
        if (data.status === 'ok') {
            resultDiv.innerHTML = `<span style="color: var(--success);">✅ ${data.message}</span>`;
        } else {
            resultDiv.innerHTML = `<span style="color: var(--danger);">❌ ${data.message || data.error}</span>`;
        }
    }

    // ========== FILE UPLOAD ==========
    const dropZone = document.getElementById('uploadZone');
    ['dragenter', 'dragover'].forEach(name => {
        dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.add('dragover'); }, false);
    });
    ['dragleave', 'drop'].forEach(name => {
        dropZone.addEventListener(name, (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); }, false);
    });
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    async function handleFiles(files) {
        if (!files || files.length === 0) return;
        for (let f of files) {
            const formData = new FormData();
            formData.append('file', f);
            try {
                await fetch('/api/upload', { method: 'POST', body: formData });
            } catch(e) { console.error('Upload error:', e); }
        }
        alert(`Загружено файлов: ${files.length}. AI начинает анализ!`);
        setTimeout(fetchProposals, 1500);
    }

    // ========== INIT ==========
    fetchStatus();
    fetchProposals();
    setInterval(fetchStatus, 5000);
    setInterval(fetchProposals, 5000);
</script>
</body>
</html>"""
        html = html_template.replace("__NTFY_TOPIC__", NTFY_TOPIC)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def run_web_server():
    server_address = ("0.0.0.0", PORT)
    httpd = ThreadedHTTPServer(server_address, HomeServerHandler)
    print(f"🌐 [Web Server] Запущен на http://0.0.0.0:{PORT}")
    httpd.serve_forever()

def start_web_server_thread():
    t = threading.Thread(target=run_web_server, daemon=True)
    t.start()
    return t





# ===== Публичные алиасы для совместимости со старым фронтендом =====

@app.get("/api/users")
async def api_users_public():
    """Возвращает список всех пользователей (без авторизации для локального доступа)."""
    from core.auth_manager import list_all_users
    return list_all_users()

@app.get("/api/token_stats")
async def api_token_stats_public():
    """Возвращает статистику токенов по пользователям."""
    from core.token_tracker import load_token_stats
    stats = load_token_stats()
    users_stats = []
    for username, data in stats.get("users", {}).items():
        users_stats.append({
            "username": username,
            "total_tokens": data.get("total_tokens", 0),
            "prompt_tokens": data.get("prompt_tokens", 0),
            "completion_tokens": data.get("completion_tokens", 0),
            "requests_count": data.get("requests_count", 0),
            "quota": data.get("token_quota", 50000),
            "models": list(data.get("models_usage", {}).keys())
        })
    return users_stats

@app.post("/api/update_quota")
async def api_update_quota_public(request: Request):
    """Обновляет квоту пользователя (без авторизации для локального доступа)."""
    data = await request.json()
    username = data.get("username")
    quota = data.get("quota")
    if quota is None:
        quota = -1
    from core.token_tracker import set_user_quota
    ok = set_user_quota(username, quota)
    return {"success": ok}

@app.post("/api/reset_tokens")
async def api_reset_tokens_public(request: Request):
    """Сбрасывает статистику токенов пользователя (без авторизации для локального доступа)."""
    data = await request.json()
    username = data.get("username")
    from core.token_tracker import reset_user_tokens
    ok = reset_user_tokens(username)
    return {"success": ok}

if __name__ == "__main__":
    print(f"Starting standalone web server on port {PORT}...")
    run_web_server()