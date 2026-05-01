"""アプリケーション設定"""

import os

DEBUG = True
SECRET_KEY = "flask-secret-key-abc123"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///users.db")
ALLOWED_HOSTS = ["*"]
CORS_ORIGINS = "*"
