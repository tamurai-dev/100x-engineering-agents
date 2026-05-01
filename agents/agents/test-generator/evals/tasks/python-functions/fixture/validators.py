"""入力バリデーション関数群"""

from __future__ import annotations

import re


def validate_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_phone(phone: str, country_code: str = "JP") -> bool:
    if not phone or not isinstance(phone, str):
        return False
    digits = re.sub(r"[\s\-\(\)]", "", phone)
    if country_code == "JP":
        return bool(re.match(r"^(0\d{9,10}|\+81\d{9,10})$", digits))
    if country_code == "US":
        return bool(re.match(r"^(\+?1)?\d{10}$", digits))
    return len(digits) >= 7


def sanitize_input(text: str, max_length: int = 1000) -> str:
    if not isinstance(text, str):
        raise TypeError(f"Expected str, got {type(text).__name__}")
    text = text.strip()
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if len(text) > max_length:
        text = text[:max_length]
    return text
