import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
FORGE_URL = os.getenv("FORGE_URL", "http://localhost:7860")
API_USER = os.getenv("API_USER", "")
API_PASS = os.getenv("API_PASS", "")
API_AUTH = (API_USER, API_PASS)
MODE = os.getenv("MODE", "PROD")

allowed_users_list = [int(user_id)  for user_id in os.getenv("ALLOWED_USERS", "").split(",")]
ALLOWED_USERS = set(allowed_users_list)
ADMINS = {ADMIN_USER_ID}
ALLOWED_USERS = ADMINS | ALLOWED_USERS

# Дефолтные параметры генерации
DEFAULTS = {
    "steps": 25,
    "cfg_scale": 7.0,
    "width": 512,
    "height": 768,  # портретный формат по умолчанию
    "sampler": "DPM++ 2M Karras",
    "negative_prompt": "blurry, lowres, bad anatomy, bad hands, text, watermark",
}

MODELS = {
    "🎨 Реализм": "realisticVisionV51_v51VAE.safetensors",
    "🌸 Аниме (boleromixPon)": "boleromixPony_v233.safetensors",
    "✨ Анимк (confettiComradeMix)": "confettiComradeMix_confettiComradeMix.safetensors",
}

PRESETS = {
    # Ключ (ASCII) → используется в callback_data
    # Значение → настройки + отображаемое имя
    "portrait": {
        "name": "📸 Портрет",  # 👈 это покажем на кнопке
        "prompt_suffix": ", portrait, detailed face, soft lighting, studio",
        "negative_suffix": ", deformed, ugly, bad proportions",
        "width": 512, "height": 768, "steps": 30
    },
    "cityscape": {
        "name": "🌆 Город",
        "prompt_suffix": ", cityscape, neon lights, cyberpunk, detailed background",
        "negative_suffix": ", blurry, empty, low detail",
        "width": 768, "height": 512, "steps": 25
    },
    "anime_art": {
        "name": "🎨 Аниме-арт",
        "prompt_suffix": ", anime style, detailed eyes, vibrant colors, masterpiece",
        "negative_suffix": ", realistic, photo, 3d render",
        "width": 512, "height": 768, "steps": 28
    },
}

DB_LAYER = "aiosqlite"  # "peewee" | "aiosqlite" | "both" (для тестов)
# Абсолютный путь к корню проекта (где лежит этот файл)
# Абсолютный путь к корню проекта (где лежит этот файл)
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = str(PROJECT_ROOT / "bot_data.db")