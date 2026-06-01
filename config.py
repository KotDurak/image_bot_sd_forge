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

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "boleromixPony_v233")
SETTING_MODEL_MAP = {
    "juggernautXL_v9Rdphoto2Lightning": {
        "steps": 6,  # Lightning любит быстро
        "cfg_scale": 1.5,  # Низкий CFG = меньше артефактов
        "width": 832,  # SDXL-родное разрешение (вертикаль)
        "height": 1216,
        "negative_suffix": "(extra limbs, extra legs, extra arms, duplicate, multiple people, deformed, bad anatomy, bad hands:1.2), lowres, blurry, watermark",
        "sampler_name": "DPM++ SDE",
        "scheduler": "karras",
    },
    "boleromixPony_v233": {
        "prompt_prefix": "score_9, score_8_up, score_7_up, source_anime, masterpiece, ultra-detailed, best quality",
        "prompt_suffix": ", cinematic lighting",
        "negative_suffix": "score_4, score_5, score_6, worst quality,worst detail, low quality, 3d, realistic",
        "width": 832,
        "height": 1216,
        "steps": 32,
        "cfg_scale": 5.4,
        "sampler_name": "DPM++ 2M SDE",
        "scheduler": "Karras"
    }
}

DEFAULTS = SETTING_MODEL_MAP[DEFAULT_MODEL]

# 🖼 Модели
MODELS = {
    "🎨 Реализм": "realisticVisionV51_v51VAE.safetensors",
    "🌸 Аниме (boleromixPon)": "boleromixPony_v233.safetensors",
    "✨ Аниме (confettiComradeMix)": "confettiComradeMix_confettiComradeMix.safetensors",
}

SEED = - 1
# Спасите, я уже 4 ночи подряд не сплю до 2 ночи! Уберите от меня змею! (подпись Кот Барсик)
HAND_FIXERS = {
    'boleromixPony_v233': {
        'hands_str': ',handfixer, <lora:HandFixer_pdxl_Incrs_v1:0.45>',
        'hands_negative': ', bad anatomy, bad hands, (extra fingers:1.1), (missing fingers:1.1), (fused fingers:1.1), malformed hands,bad fingers, deformed hands, interlocked fingers, anatomically incorrect hands',
        'preset_key': ['anime_art', 'anime_art_vertical']
    }
}


PRESETS = {
    "anime_art": {
        "name": "🎨 Аниме-Универсал (832x1216)",
        "prompt_prefix": "score_9, score_8_up, score_7_up, source_anime, masterpiece, ultra-detailed, best quality",
        "prompt_suffix": ", cinematic lighting",
        "negative_suffix": "score_4, score_5, score_6, worst quality,worst detail, low quality, 3d, realistic",
        "width": 832,
        "height": 1216,
        "steps": 32,
        "cfg_scale": 5.4,
        "sampler": "DPM++ 2M SDE",
        "scheduler": "Karras"
    },
    "anime_art_vertical": {
        "name": "🎨 Аниме-Универсал (1216x832)",
        "prompt_prefix": "score_9, score_8_up, score_7_up, source_anime, masterpiece, ultra-detailed, best quality",
        "prompt_suffix": ", cinematic lighting",
        "negative_suffix": "score_4, score_5, score_6, worst quality,worst detail, low quality, 3d, realistic",
        "width": 1216,
        "height": 832,
        "steps": 32,
        "cfg_scale": 5.4,
        "sampler": "DPM++ 2M SDE",
        "scheduler": "Karras"
    },
    "realism": {
        "name": "📸 Реализм (Juggernaut)",
        "prompt_prefix": "",
        "prompt_suffix": ", masterpiece, best quality, detailed skin, soft lighting",
        "negative_suffix": "(extra limbs, extra legs, extra arms, duplicate, multiple people, deformed, bad anatomy, bad hands:1.2), lowres, blurry, watermark, text, signature",
        "width": 832,
        "height": 1216,
        "steps": 6,  # ⚡ Lightning любит быстро
        "cfg_scale": 1.5,  # 🔥 Низкий CFG для реализма
        "sampler": "DPM++ SDE",
        "scheduler": "karras"
    }
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

PRESET_LIMITS = {
    "steps_min": 1,  # Минимум: хозяин барин
    "steps_max": 50,  # Максимум: защита от перегрузки GPU
    "cfg_min": 1.0,  # Минимальный CFG
    "cfg_max": 30.0,  # Максимальный CFG
    "res_min": 256,  # Мин. сторона разрешения
    "res_max": 1344,  # Макс. сторона (поменяйте на 2048, если Forge тянет)
    "name_max_len": 30,  # Макс. длина имени пресета
    "divisor": 8  # Шаг кратности разрешения
}

PLATEGA_API_URL = "https://app.platega.io"
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID")
PLATEGA_API_KEY = os.getenv("PLATEGA_API_KEY")
ENABLE_ADETAILER= os.getenv("ENABLE_ADETAILER", "false").lower() == "true"

ADETAILER_HAND_CFG_OLD = {
    "ad_model": "hand_yolov8n.pt",
    "ad_prompt": "score_9, score_8_up, score_7_up, 5 fingers, perfect hands",
    "ad_negative_prompt": "",          # 🔧 Pydantic v2 ломается на строке "None". Пустая строка = безопасный ноль.
    "ad_confidence": 0.30,
    "ad_denoising_strength": 0.58,
    "ad_mask_blur": 4,
    "ad_padding": 32,
    "ad_inpaint_width": 0,
    "ad_inpaint_height": 0,
    "ad_restore_face": False,
    "ad_inpaint_only_masked": True,
    "ad_steps": 12
}

ADETAILER_HAND_CFG = {
    "ad_model": "hand_yolov8n.pt",
    "ad_prompt": "beautiful detailed hands, correct hand anatomy, natural hand pose",
    "ad_negative_prompt": "extra fingers, fused fingers, malformed hands, bad hands, mutated fingers, missing fingers",
    "ad_confidence": 0.35,
    "ad_denoising_strength": 0.38,
    "ad_mask_blur": 4,
    "ad_padding": 32,
    "ad_inpaint_width": 0,
    "ad_inpaint_height": 0,
    "ad_restore_face": False,
   # "ad_inpaint_only_masked": False,
    "ad_steps": 16
}