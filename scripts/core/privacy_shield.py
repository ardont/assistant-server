# -*- coding: utf-8 -*-
"""
Privacy Shield Module for HomeServer
Sanitizes and anonymizes Personally Identifiable Information (PII), credentials,
financial data, and personal identifiers BEFORE sending text snippets to any Cloud LLM.
"""
import re
from typing import Tuple, List, Dict

# Regex Patterns for Sensitive Russian and Global Data
PII_PATTERNS = [
    # 1. Credit / Debit Cards (16 digits with optional dashes/spaces)
    (r"\b(?:\d{4}[ -]?){3}\d{4}\b", "[БАНКОВСКАЯ_КАРТА]"),
    
    # 2. Russian Passport (4 digits series + 6 digits number)
    (r"\b\d{2}\s?\d{2}\s+\d{6}\b", "[ПАСПОРТ_РФ]"),
    (r"\bпаспорт(?:\s+РФ)?[\s:№]+(\d{4}\s?\d{6})\b", "[ПАСПОРТ_РФ]"),
    
    # 3. Phone Numbers (+7, 8, +375, etc.)
    (r"(?:\+7|8|7)[\s\(\)-]?\(?\d{3}\)?[\s\(\)-]?\d{3}[\s\(\)-]?\d{2}[\s\(\)-]?\d{2}", "[ТЕЛЕФОН]"),
    (r"\b\+\d{1,3}[\s\(\)-]?\d{2,4}[\s\(\)-]?\d{2,4}[\s\(\)-]?\d{2,4}\b", "[ТЕЛЕФОН]"),
    
    # 4. Email Addresses
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
    
    # 5. SNILS (СНИЛС: 123-456-789 01 or 123-456-789-01)
    (r"\b\d{3}-\d{3}-\d{3}[\s-]?\d{2}\b", "[СНИЛС]"),
    
    # 6. INN (ИНН: 10 or 12 digits)
    (r"\bИНН[\s:№]+(\d{10}|\d{12})\b", "[ИНН]"),
    
    # 7. Bank Accounts (20-digit Russian settlement accounts 40817..., 40702...)
    (r"\b(?:40702|40817|40802|30101|42301)\d{15}\b", "[БАНКОВСКИЙ_СЧЕТ]"),
    
    # 8. API Keys, Tokens, Passwords, Private Keys
    (r"(?:api[_-]?key|secret|password|bearer|token|пароль)[\s:=\"']+([A-Za-z0-9_\-\.]{12,})", "[API_КЛЮЧ_ИЛИ_ПАРОЛЬ]"),
    (r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+PRIVATE KEY-----", "[ПРИВАТНЫЙ_КЛЮЧ]"),
    (r"\b(?:AIza|AQ\.|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,})\b", "[API_КЛЮЧ]")
]

def sanitize_text(text: str) -> Tuple[str, List[str]]:
    """
    Sanitizes text and returns:
    1. Anonymized text with safe placeholders
    2. List of detected PII categories
    """
    if not text:
        return "", []
        
    sanitized = text
    detected_types = []
    
    for pattern, replacement in PII_PATTERNS:
        matches = re.findall(pattern, sanitized, flags=re.IGNORECASE)
        if matches:
            detected_types.append(replacement.strip("[]"))
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
            
    return sanitized, list(set(detected_types))

if __name__ == "__main__":
    test_sample = """
    Договор на разработку.
    Заказчик: Иванов Иван. Телефон: +7 (999) 123-45-67, почта: ivan.ivanov@mail.ru
    Паспорт серия 4510 номер 123456.
    Оплата на карту 4276 3800 1234 5678 или счет 40817810000000012345.
    Ключ API для тестов: sk-sample-test-placeholder-key.
    """
    clean, pii = sanitize_text(test_sample)
    print("=== Исходный текст ===")
    print(test_sample)
    print("=== Обезличенный текст (отправляется в Gemini) ===")
    print(clean)
    print("=== Обнаруженные типы данных ===", pii)
