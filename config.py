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
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")

# 👥 Доступ
ALLOWED_USERS = {
    int(uid) for uid in os.getenv("ALLOWED_USERS", "").split(",") if uid.strip()
} | {ADMIN_USER_ID}

# 🎛 Режим работы: "DEV" или "PROD"
MODE = os.getenv("MODE", "PROD").upper()

# 🎯 Модель по умолчанию - Nova Anime XL
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "novaAnimeXL_ilV140")

SETTING_MODEL_MAP = {
    "novaAnimeXL_ilV190": {
        "clip_skip": 2,  # Подтверждено для Nova/Illustrious
        "prompt_prefix": "masterpiece, best quality, amazing quality, 4k, very aesthetic, high resolution, ultra-detailed, absurdres, newest, 1girl, solo",
        "prompt_suffix": "BREAK, depth of field, volumetric lighting",
        "negative_suffix": "modern, recent, old, oldest, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, long body, lowres, bad anatomy, bad hands, missing fingers, extra digits, fewer digits, cropped, very displeasing, (worst quality, bad quality:1.2), bad anatomy, sketch, jpeg artifacts, signature, watermark, username, signature, simple background, conjoined, bad ai-generated",
        "width": 832,
        "height": 1216,
        "steps": 20,  # ← ЗОЛОТОЙ СТАНДАРТ
        "cfg_scale": 4.5,  # ← ЗОЛОТОЙ СТАНДАРТ
        "sampler_name": "Euler a",  # Или DPM++ 2M Karras (оба работают)
        "scheduler": "Karras"
    },

    "novaAnimeXL_ilV180": {
        "clip_skip": 2,
        "prompt_prefix": "masterpiece, best quality, amazing quality, 4k, very aesthetic, high resolution, ultra-detailed, absurdres, newest, 1girl, solo",
        "prompt_suffix": "BREAK, depth of field, volumetric lighting",
        "negative_suffix": "modern, recent, old, oldest, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, long body, lowres, bad anatomy, bad hands, missing fingers, extra digits, fewer digits, cropped, very displeasing, (worst quality, bad quality:1.2), bad anatomy, sketch, jpeg artifacts, signature, watermark, username, signature, simple background, conjoined, bad ai-generated",
        "width": 832,
        "height": 1216,
        "steps": 20,
        "cfg_scale": 5.0,
        "sampler_name": "DPM++ 2M Karras",
        "scheduler": "Karras"
    },

    "novaAnimeXL_ilV140": {
        "clip_skip": 2,
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes",
        "prompt_suffix": "",
        "negative_suffix": "modern, recent, old, oldest, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, long body, lowres, bad anatomy, bad hands, missing fingers, extra digits, fewer digits, cropped, very displeasing, (worst quality, bad quality:1.2), bad anatomy, sketch, jpeg artifacts, signature, watermark, username, signature, simple background, conjoined, bad ai-generated",
        "width": 832,
        "height": 1216,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler_name": "Euler a",
        "scheduler": "Karras"
    }
}

DEFAULTS = SETTING_MODEL_MAP[DEFAULT_MODEL]

# 🖼 Модели - только Nova
MODELS = {
    "🌟 Nova Anime XL": "novaAnimeXL_ilV190.safetensors",
}

SEED = -1
# Спасите, я уже 4 ночи подряд не сплю до 2 ночи! Уберите от меня змею! (подпись Кот Барсик)
HANDFIXER_WEIGHT = '0.6'

HAND_FIXERS = {
    'novaAnimeXL_ilV140': {
        'hands_str': '',  # ← ПУСТО! Модель справляется сама
        'hands_negative': 'bad hands, missing fingers, extra digit, fused fingers, malformed hands',
        'preset_key': ['nova_anime_vertical', 'nova_anime_horizontal', 'nova_anime_square', 'nova_anime_vertical_modern']
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
ADS_FOR_FREE_ONLY = os.getenv("ADS_FOR_FREE_ONLY", "false").lower() == "true"
ADS_PAID_CHANCE = float(os.getenv("ADS_PAID_CHANCE", "0.1"))

AD_REPORT_ANONYMIZE = os.getenv("AD_REPORT_ANONYMIZE", "true").lower() == "true"
AD_REPORT_SALT = os.getenv("AD_REPORT_SALT", "change_me_in_prod")

# 🌍 Настройки языка и перевода
SHOW_LANGUAGE_WARNING = os.getenv("SHOW_LANGUAGE_WARNING", "true").lower() == "true"
ENABLE_FREE_TRANSLATE = os.getenv("ENABLE_FREE_TRANSLATE", "false").lower() == "true"

# ⚠️ Предупреждение для пользователей
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
    "steps_min": 1,
    "steps_max": 50,
    "cfg_min": 1.0,
    "cfg_max": 30.0,
    "res_min": 256,
    "res_max": 1344,
    "name_max_len": 30,
    "divisor": 8
}

PLATEGA_API_URL = "https://app.platega.io"
PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID")
PLATEGA_API_KEY = os.getenv("PLATEGA_API_KEY")

# 🔥 ВАЖНО: Включи это, если хочешь, чтобы ADetailer чинил руки автоматически!
ENABLE_ADETAILER = os.getenv("ENABLE_ADETAILER", "true").lower() == "true"

ADETAILER_HAND_CFG_OLD = {
    "ad_model": "hand_yolov8n.pt",
    "ad_prompt": "score_9, score_8_up, score_7_up, 5 fingers, perfect hands",
    "ad_negative_prompt": "",
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
    "ad_steps": 16
}

WEBAPP_URL = os.getenv("WEBAPP_URL", 'https://kotdurak.github.io/prompt_generator')

LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL")