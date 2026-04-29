"""
 Конфигурация бота.
"""
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# 🔑 Telegram & API
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
ADMINS = [ADMIN_USER_ID]

# 🎨 Stable Diffusion Forge
FORGE_URL = os.getenv("FORGE_URL", "http://localhost:7860")
API_USER = os.getenv("API_USER", "")
API_PASS = os.getenv("API_PASS", "")
API_AUTH = (API_USER, API_PASS) if API_USER and API_PASS else None

# 👥 Доступ
ALLOWED_USERS = {
    int(uid) for uid in os.getenv("ALLOWED_USERS", "").split(",") if uid.strip()
} | {ADMIN_USER_ID}

# 🎛 Режим работы: "DEV" или "PROD"
MODE = os.getenv("MODE", "PROD").upper()

# 🎨 Дефолты генерации
DEFAULTS = {
    "steps": 6,                    # Lightning любит быстро
    "cfg_scale": 1.5,              # Низкий CFG = меньше артефактов
    "width": 832,                  # SDXL-родное разрешение (вертикаль)
    "height": 1216,
    "negative_prompt": "blurry, lowres, bad anatomy, bad hands, text, watermark, ugly, deformed, noisy",
    "sampler_name": "DPM++ 2M",
    "scheduler": "karras",
}

# 🖼 Модели
MODELS = {
    "🎨 Реализм": "realisticVisionV51_v51VAE.safetensors",
    "🌸 Аниме (boleromixPon)": "boleromixPony_v233.safetensors",
    "✨ Аниме (confettiComradeMix)": "confettiComradeMix_confettiComradeMix.safetensors",
}

# 🎭 Пресеты
PRESETS = {
    "portrait": {
        "name": "📸 Портрет",
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

SAMPLERS = {
    "Euler ⚡": "Euler",
    "Euler a 🌊": "Euler a",
    "LMS 🧮": "LMS",
    "Heun 🧪": "Heun",
    "DPM2 🎲": "DPM2",
    "DPM2 a 🎲": "DPM2 a",
    "DPM++ 2S a ⚡": "DPM++ 2S a",
    "DPM++ 2M 🎯": "DPM++ 2M",
    "DPM++ SDE 💧": "DPM++ SDE",
    "DPM++ 2M SDE 🔬": "DPM++ 2M SDE",
    "DPM++ 3M SDE 🧠": "DPM++ 3M SDE",
    "UniPC 🚀": "UniPC",
    "DDIM 📜": "DDIM",
    "PLMS 📐": "PLMS"
}

# 🔥 FIX: значения шедулеров — с большой буквы, как ждёт Forge API
SCHEDULERS = {
    "Automatic 🤖": "automatic",
    "Uniform 📏": "uniform",
    "Karras 📈": "karras",
    "Exponential 🧬": "exponential",
    "Polyexponential 🌊": "polyexponential",
    "SGM Uniform ⚖️": "sgm_uniform",
    "KL Optimal 🎯": "kl_optimal",
    "Align Your Steps 🚶": "align_your_steps",
    "Simple ⚡": "simple",
    "Normal 📉": "normal",
    "DDIM 📜": "ddim",
    "Beta 🧪": "beta",
    "Turbo 🚀": "turbo",
    "AYS GITS 🧠": "align_your_steps_GITS",
    "AYS 11 🔢": "align_your_steps_11",
    "AYS 32 🔢": "align_your_steps_32",
}

# 🗄 База данных
DB_LAYER = "aiosqlite"
PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = str(PROJECT_ROOT / "bot_data.db")

# 📁 Пути
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# 📢 Настройки рекламы
ADS_ENABLED = os.getenv("ADS_ENABLED", "true").lower() == "true"
ADS_FOR_FREE_ONLY = os.getenv("ADS_FOR_FREE_ONLY", "false").lower() == "true"  # если true — платным не показываем
ADS_PAID_CHANCE = float(os.getenv("ADS_PAID_CHANCE", "0.1"))  # 10% шанс показать платному

AD_REPORT_ANONYMIZE = os.getenv("AD_REPORT_ANONYMIZE", "true").lower() == "true"
AD_REPORT_SALT = os.getenv("AD_REPORT_SALT", "change_me_in_prod")  # Соль для хеширования

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "juggernautXL_v9Rdphoto2Lightning")

# 🌍 Настройки языка и перевода
SHOW_LANGUAGE_WARNING = os.getenv("SHOW_LANGUAGE_WARNING", "true").lower() == "true"
ENABLE_FREE_TRANSLATE = os.getenv("ENABLE_FREE_TRANSLATE", "false").lower() == "true"

# ⚠️ Предупреждение для пользователей (показывается, если промпт не на латинице)
PROMPT_LANGUAGE_WARNING = (
    "⚠️ *Совет*: пиши промпты на **английском** — так нейросеть поймёт тебя точнее.\n"
    "Можешь использовать Google Translate: даже простой перевод даст лучший результат."
)

EMAIL = os.getenv('EMAIL', '')
HIDDEN_LORAS = {
    x.strip().lower()
    for x in os.getenv("FORGE_HIDDEN_LORAS", "").split(",")
    if x.strip()
}