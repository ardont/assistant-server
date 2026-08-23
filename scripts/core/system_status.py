"""
System Status Monitoring Module
"""
import sys
import psutil
import datetime

# Fix Windows console UTF-8 encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def get_system_metrics():
    cpu_percent = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.datetime.now() - boot_time
    
    return {
        "cpu_percent": cpu_percent,
        "ram_used_gb": round(mem.used / (1024**3), 2),
        "ram_total_gb": round(mem.total / (1024**3), 2),
        "ram_percent": mem.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_percent": disk.percent,
        "uptime_hours": round(uptime.total_seconds() / 3600, 1)
    }

def get_status_text():
    m = get_system_metrics()
    return (
        f"💻 Статус HomeServer:\n"
        f"⏱️ Аптайм: {m['uptime_hours']} ч\n"
        f"⚡ CPU: {m['cpu_percent']}%\n"
        f"🧠 ОЗУ: {m['ram_used_gb']} / {m['ram_total_gb']} ГБ ({m['ram_percent']}%)\n"
        f"💾 Диск C: свободно {m['disk_free_gb']} ГБ из {m['disk_total_gb']} ГБ ({m['disk_percent']}% занято)"
    )

if __name__ == "__main__":
    print(get_status_text())