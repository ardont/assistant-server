# -*- coding: utf-8 -*-
"""
Audio Transcription Engine using Google Gemini Multimodal Audio API
Supports .m4a, .mp3, .wav, .aac, .ogg
"""
import os
import sys
import json
import base64
import time
import urllib.request
import urllib.error
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path("C:/HomeServer")
ENV_PATH = BASE_DIR / "config" / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)

def get_keys():
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=True)
    k1 = os.getenv("GEMINI_API_KEY", "")
    k2 = os.getenv("GEMINI_BACKUP_KEY", "")
    return [k for k in [k1, k2] if k]

def get_mime_type(suffix: str) -> str:
    s = suffix.lower().lstrip(".")
    if s in ["m4a", "mp4"]:
        return "audio/mp4"
    if s == "mp3":
        return "audio/mp3"
    if s == "wav":
        return "audio/wav"
    if s == "ogg":
        return "audio/ogg"
    if s == "aac":
        return "audio/aac"
    return "audio/mp4"

def transcribe_audio_file(audio_path: Path, prompt_text: str = None) -> dict:
    if isinstance(audio_path, str):
        audio_path = Path(audio_path)
    if not audio_path.exists():
        return {"status": "error", "message": f"Файл {audio_path} не найден"}
    
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    print(f"🎙️ [TRANSCRIBE] Чтение аудиофайла: {audio_path.name} ({file_size_mb:.2f} MB)...")
    
    mime_type = get_mime_type(audio_path.suffix)
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        
    prompt = prompt_text or (
        "Пожалуйста, сделай максимально точную, полную и грамотную расшифровку (транскрибацию) этой аудиозаписи на русском языке. "
        "В начале выдели краткую суть разговора (Summary / Ключевые мысли), затем предоставь полный дословный текст."
    )
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": audio_b64
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192
        }
    }
    
    gemini_keys = get_keys()
    models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    
    for key in gemini_keys:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            try:
                print(f"  -> Отправка в Gemini API ({model})...")
                with urllib.request.urlopen(req, timeout=120) as resp:
                    if resp.status == 200:
                        res = json.loads(resp.read().decode("utf-8"))
                        text = res["candidates"][0]["content"]["parts"][0]["text"]
                        
                        out_txt = audio_path.parent / f"{audio_path.stem}_транскрипция.txt"
                        out_md = audio_path.parent / f"{audio_path.stem}_транскрипция.md"
                        
                        with open(out_txt, "w", encoding="utf-8") as f_out:
                            f_out.write(text)
                        with open(out_md, "w", encoding="utf-8") as f_out:
                            f_out.write(f"# 🎙️ Транскрипция аудио: {audio_path.name}\n\n" + text)
                            
                        print(f"  [✓] Успешно расшифровано! Сохранено в: {out_txt.name}")
                        return {
                            "status": "ok",
                            "model": model,
                            "text": text,
                            "txt_path": str(out_txt),
                            "md_path": str(out_md)
                        }
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                print(f"  [!] HTTP {e.code} ({model}): {err_body[:120]}")
            except Exception as e:
                print(f"  [!] Ошибка ({model}): {e}")
                
    return {"status": "error", "message": "Не удалось расшифровать аудиозапись через доступные ключи/модели"}
