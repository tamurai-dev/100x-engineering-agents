"""認証モジュール"""

import jwt

SECRET_KEY = "my-super-secret-jwt-key-12345"


def create_token(user_id: int, role: str = "user") -> str:
    payload = {"user_id": user_id, "role": role}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def verify_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except:
        return None
