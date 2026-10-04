"""
Пресеты генерации для разных моделей и стилей.
Каждый пресет содержит настройки для Stable Diffusion / Forge API.
"""

# ==========================================
# БАЗОВЫЕ ПРЕСЕТЫ (Euler a - мягкий, аниме-стиль)
# ==========================================

PRESETS = {
    # --- Вертикальные ---
    "nova_anime_vertical": {
        "name": "🌟 Nova Anime XL (Вертикаль 832x1216)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, 3d, realistic, ugly",
        "width": 832,
        "height": 1216,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Automatic"
    },

    "nova_anime_vertical_modern": {
        "name": "✨ Nova Anime Modern (Объем и глубокие тени)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, ugly",
        "width": 832,
        "height": 1216,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Automatic"
    },

    # --- Горизонтальные ---
    "nova_anime_horizontal": {
        "name": "🌟 Nova Anime XL (Горизонталь 1216x832)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, 3d, realistic, ugly",
        "width": 1216,
        "height": 832,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Automatic"
    },

    # --- Квадратные ---
    "nova_anime_square": {
        "name": "🌟 Nova Anime XL (Квадрат 1024x1024)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, 3d, realistic, ugly",
        "width": 1024,
        "height": 1024,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Automatic"
    },

    # ==========================================
    # ПРЕСЕТЫ С DPM++ 2M Karras (четкие линии, детализация)
    # ==========================================

    "nova_anime_dpm_vertical": {
        "name": "⚡ Nova Anime DPM (Вертикаль, четкие линии)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, 3d, realistic, ugly",
        "width": 832,
        "height": 1216,
        "steps": 25,
        "cfg_scale": 5.5,
        "sampler": "DPM++ 2M",
        "scheduler": "Karras"
    },

    "nova_anime_dpm_horizontal": {
        "name": "⚡ Nova Anime DPM (Горизонталь, четкие линии)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, 3d, realistic, ugly",
        "width": 1216,
        "height": 832,
        "steps": 25,
        "cfg_scale": 5.5,
        "sampler": "DPM++ 2M",
        "scheduler": "Karras"
    },

    "nova_anime_dpm_square": {
        "name": "🌟 Nova Anime DPM (Квадрат, четкие линии)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, 3d, realistic, ugly",
        "width": 1024,
        "height": 1024,
        "steps": 25,
        "cfg_scale": 5.5,
        "sampler": "DPM++ 2M",
        "scheduler": "Karras"
    },

    # ==========================================
    # СПЕЦИАЛЬНЫЕ ПРЕСЕТЫ
    # ==========================================

    "nova_anime_portrait": {
        "name": " Nova Anime Portrait (Крупный план лица)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style, detailed face",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad hands, missing fingers, extra digit, text, watermark, 3d, realistic, ugly, deformed face",
        "width": 768,
        "height": 1024,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Automatic"
    },

    "nova_anime_cinematic": {
        "name": "🎬 Nova Anime Cinematic (Кинематографичный)",
        "prompt_prefix": "masterpiece, best quality, highres, beautiful detailed eyes, anime style, cinematic lighting, dramatic shadows",
        "prompt_suffix": "",
        "negative_suffix": "worst quality, low quality, bad anatomy, bad proportions, bad hands, missing fingers, extra digit, text, watermark, ugly",
        "width": 1216,
        "height": 832,
        "steps": 25,
        "cfg_scale": 5.0,
        "sampler": "DPM++ 2M",
        "scheduler": "Karras"
    },
}

# Пресет по умолчанию
DEFAULT_PRESET_KEY = "nova_anime_vertical"


def get_preset_list() -> list:
    """
    Возвращает список кортежей: [(технический_ключ, отображаемое_имя), ...]
    """
    return [(key, cfg["name"]) for key, cfg in PRESETS.items()]


def apply_preset(base_prompt: str, preset_key: str) -> dict:
    """
    Применяет пресет по техническому ключу.
    Возвращает словарь с настройками генерации.
    """
    preset = PRESETS.get(preset_key, PRESETS[DEFAULT_PRESET_KEY])

    return {
        "prompt": base_prompt + preset.get("prompt_suffix", ""),
        "negative_prompt": preset.get("negative_suffix", ""),
        "width": preset.get("width", 832),
        "height": preset.get("height", 1216),
        "steps": preset.get("steps", 20),
        "cfg_scale": preset.get("cfg_scale", 4.5),
        "sampler": preset.get("sampler", "Euler a"),
        "scheduler": preset.get("scheduler", "Automatic")
    }