# -*- coding: utf-8 -*-
"""
HomeServer Sentinel (Сторож для запуска на 2-м ноутбуке)
- Мониторит здоровье основного сервера каждые 30 секунд
- Оповещает через звуковой сигнал и push-уведомление ntfy при падении сервера
- Показывает нагрузку на память и аптайм основного сервера
"""
import time
import json
import urllib.request
import urllib.error
import datetime

# Адреса основного сервера (сначала локальный Wi-Fi, потом Tailscale)
SERVER_URLS = [
    "http://192.168.50.108:8000",
    "http://100.110.6.52:8000",
    "http://localhost:8000"
]
NTFY_TOPIC = "homeserver_user_2026"

def check_server():
    for url in SERVER_URLS:
        try:
            req = urllib.request.Request(f"{url}/api/health", headers={"User-Agent": "Sentinel/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return url, data
        except Exception:
            continue
    return None, None

def send_alert(msg):
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            data=msg.encode("utf-8"),
            headers={"Title": "⚠️ HomeServer Внимание!".encode("utf-8"), "Priority": "high", "Tags": "warning"}
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

def main():
    print("=" * 65)
    print("🛡️ HomeServer Sentinel (Сторож основного сервера) Запущен")
    print("=" * 65)
    print(f"Целевые адреса: {', '.join(SERVER_URLS)}")
    print("Интервал проверки: 30 секунд\n")
    
    consecutive_failures = 0
    
    while True:
        active_url, health = check_server()
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        
        if health:
            consecutive_failures = 0
            rss = health.get("process_ram_mb", "N/A")
            uptime = health.get("server_uptime", "N/A")
            avail_gb = health.get("system_ram_available_gb", "N/A")
            print(f"[{now_str}] [✓ ОНЛАЙН] {active_url} | Аптайм: {uptime} | RAM: {rss} МБ | Свободно в системе: {avail_gb} ГБ")
        else:
            consecutive_failures += 1
            print(f"[{now_str}] [🚨 ОФФЛАЙН] Основной сервер не отвечает! (Попытка {consecutive_failures})")
            if consecutive_failures == 3:
                print(">>> Отправка экстренного Push-уведомления...")
                send_alert("Основной HomeServer не отвечает более 90 секунд!")
        
        time.sleep(30)

if __name__ == "__main__":
    main()
