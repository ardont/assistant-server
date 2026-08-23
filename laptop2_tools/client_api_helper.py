# -*- coding: utf-8 -*-
"""
HomeServer API Client Helper for Laptop 2
Позволяет легко из любого Python-скрипта на 2-м ноутбуке:
- Отправлять файлы в INBOX сервера
- Задавать вопросы AI чату
- Получать задачи из учебного плана
"""
import urllib.request
import urllib.parse
import json

class HomeServerClient:
    def __init__(self, host="http://192.168.50.108:8000"):
        self.host = host.rstrip("/")

    def ping(self):
        try:
            req = urllib.request.Request(f"{self.host}/api/health")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def ask_ai(self, question: str) -> str:
        url = f"{self.host}/api/chat"
        data = json.dumps({"message": question}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return res.get("response", "")

    def send_note(self, text: str, tag: str = "заметка"):
        url = f"{self.host}/api/inbox/quick_note"
        data = json.dumps({"text": text, "tag": tag}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

if __name__ == "__main__":
    client = HomeServerClient()
    print("Тест связи с сервером:", client.ping())
