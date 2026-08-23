# -*- coding: utf-8 -*-
"""
Notification Engine for HomeServer (ntfy.sh + Email + Logging)
"""
import os
import sys
import smtplib
import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path("C:/HomeServer")
ENV_PATH = BASE_DIR / "config" / ".env"
LOG_DIR = BASE_DIR / "logs"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)

NTFY_TOPIC = os.getenv("NTFY_TOPIC", "homeserver_user_2026")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")

def log_event(level: str, title: str, message: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"notifications_{datetime.date.today().strftime('%Y%m%d')}.log"
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] [{level.upper()}] {title}: {message}\n")

def send_push(title: str, message: str, priority: str = "default", tags: str = "computer") -> bool:
    try:
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": priority,
            "Tags": tags
        }
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=5)
        log_event("PUSH", title, f"Status: {resp.status_code}")
        return resp.status_code == 200
    except Exception as e:
        log_event("PUSH_ERROR", title, str(e))
        return False

def send_email(subject: str, body: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not ALERT_EMAIL_TO:
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_EMAIL_TO
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [ALERT_EMAIL_TO], msg.as_string())
        server.quit()
        log_event("EMAIL", subject, "Sent successfully")
        return True
    except Exception as e:
        log_event("EMAIL_ERROR", subject, str(e))
        return False

def notify_info(title: str, message: str) -> bool:
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ℹ️ [УВЕДОМЛЕНИЕ] {title}: {message}")
    return send_push(title, message, priority="default", tags="information_source")

def notify_success(title: str, message: str) -> bool:
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ [УСПЕХ] {title}: {message}")
    return send_push(title, message, priority="default", tags="white_check_mark")

def notify_warning(title: str, message: str) -> bool:
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚠️ [ПРЕДУПРЕЖДЕНИЕ] {title}: {message}")
    return send_push(title, message, priority="high", tags="warning")

def notify_error(title: str, message: str) -> bool:
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] 🚨 [ОШИБКА] {title}: {message}")
    send_email(f"[HomeServer ALERT] {title}", message)
    return send_push(title, message, priority="urgent", tags="rotating_light")

def notify_calendar_event(title: str, date_str: str) -> bool:
    return send_push(f"📅 Новое событие: {title}", f"Запланировано на: {date_str}", priority="high", tags="calendar")
