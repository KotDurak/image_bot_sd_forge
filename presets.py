"""
Пресеты генерации для novaAnimeXL_ilV190 (Illustrious-based).
Оптимизированы для максимальной четкости, детализации и отсутствия "мыла".
"""

# ==========================================
# МАГИЧЕСКИЕ ТЕГИ ДЛЯ V190 (Illustrious/Nova)
# ==========================================
V190_PREFIX = "masterpiece, best quality, amazing quality, 4k, very aesthetic, high resolution, ultra-detailed, absurdres, newest"
V190_SUFFIX = "BREAK, depth of field, volumetric lighting"
V190_NEGATIVE = "modern, recent, old, oldest, cartoon, graphic, text, painting, crayon, graphite, abstract, glitch, deformed, mutated, ugly, disfigured, long body, lowres, bad anatomy, bad hands, missing fingers, extra digits, fewer digits, cropped, very displeasing, (worst quality, bad quality:1.2), bad anatomy, sketch, jpeg artifacts, signature, watermark, username, signature, simple background, conjoined, bad ai-generated, blurry, out of focus"

PRESETS = {
    # ==========================================
    # БАЗОВЫЕ ПРЕСЕТЫ (Euler a - мягкий, идеальный аниме-стиль)
    # ==========================================
    "nova_anime_vertical": {
        "name": "🌟 Nova V190 (Вертикаль 832x1216)",
        "prompt_prefix": V190_PREFIX,
        "prompt_suffix": V190_SUFFIX,
        "negative_suffix": V190_NEGATIVE,
        "width": 832,
        "height": 1216,
        "steps": 20,          # 🔑 Строго 20 для V190
        "cfg_scale": 4.5,     # 🔑 Строго 4.5 для чистых цветов
        "sampler": "Euler a",
        "scheduler": "Karras" # Karras стабильнее Automatic
    },

    "nova_anime_horizontal": {
        "name": "🌟 Nova V190 (Горизонталь 1216x832)",
        "prompt_prefix": V190_PREFIX,
        "prompt_suffix": V190_SUFFIX,
        "negative_suffix": V190_NEGATIVE,
        "width": 1216,
        "height": 832,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Karras"
    },

    "nova_anime_square": {
        "name": "🌟 Nova V190 (Квадрат 1024x1024)",
        "prompt_prefix": V190_PREFIX,
        "prompt_suffix": V190_SUFFIX,
        "negative_suffix": V190_NEGATIVE,
        "width": 1024,
        "height": 1024,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Karras"
    },

    # ==========================================
    # ПРЕСЕТЫ С DPM++ 2M Karras (для более резких, графичных линий)
    # ==========================================
    "nova_anime_dpm_vertical": {
        "name": "⚡ Nova V190 DPM (Вертикаль, четкие линии)",
        "prompt_prefix": V190_PREFIX + ", sharp focus, intricate details",
        "prompt_suffix": V190_SUFFIX,
        "negative_suffix": V190_NEGATIVE + ", soft, smooth, blurry",
        "width": 832,
        "height": 1216,
        "steps": 22,          # DPM иногда требует на 2 шага больше
        "cfg_scale": 5.0,     # Чуть выше для контраста, но не больше 5.5
        "sampler": "DPM++ 2M Karras",
        "scheduler": "Karras"
    },

    "nova_anime_dpm_square": {
        "name": "⚡ Nova V190 DPM (Квадрат, четкие линии)",
        "prompt_prefix": V190_PREFIX + ", sharp focus, intricate details",
        "prompt_suffix": V190_SUFFIX,
        "negative_suffix": V190_NEGATIVE + ", soft, smooth, blurry",
        "width": 1024,
        "height": 1024,
        "steps": 22,
        "cfg_scale": 5.0,
        "sampler": "DPM++ 2M Karras",
        "scheduler": "Karras"
    },

    # ==========================================
    # СПЕЦИАЛЬНЫЕ ПРЕСЕТЫ
    # ==========================================
    "nova_anime_portrait": {
        "name": "👤 Nova V190 Portrait (Крупный план лица)",
        "prompt_prefix": V190_PREFIX + ", extreme close-up, detailed face, beautiful detailed eyes",
        "prompt_suffix": V190_SUFFIX,
        "negative_suffix": V190_NEGATIVE + ", deformed face, bad proportions, full body",
        "width": 768,
        "height": 1024,
        "steps": 20,
        "cfg_scale": 4.5,
        "sampler": "Euler a",
        "scheduler": "Karras"
    },

    "nova_anime_cinematic": {
        "name": "🎬 Nova V190 Cinematic (Кинематографичный)",
        "prompt_prefix": V190_PREFIX + ", cinematic lighting, dramatic shadows, ray tracing, masterpiece composition",
        "prompt_suffix": "BREAK, depth of field, volumetric lighting, lens flare, film grain",
        "negative_suffix": V190_NEGATIVE + ", flat lighting, oversaturated",
        "width": 1216,
        "height": 832,
        "steps": 22,
        "cfg_scale": 5.0,
        "sampler": "DPM++ 2M Karras",
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

    # Примечание: если твой основной код использует prompt_prefix отдельно,
    # убедись, что он склеивается как: prefix + base_prompt + suffix
    return {
        "prompt_prefix": preset.get("prompt_prefix", ""),
        "prompt_suffix": preset.get("prompt_suffix", ""),
        "negative_prompt": preset.get("negative_suffix", ""),
        "width": preset.get("width", 832),
        "height": preset.get("height", 1216),
        "steps": preset.get("steps", 20),
        "cfg_scale": preset.get("cfg_scale", 4.5),
        "sampler": preset.get("sampler", "Euler a"),
        "scheduler": preset.get("scheduler", "Karras")
    }