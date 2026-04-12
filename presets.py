from config import PRESETS, DEFAULTS


def get_preset_list() -> list:
    """
    Возвращает список кортежей: [(отображаемое_имя, технический_ключ), ...]
    Пример: [("📸 Портрет", "portrait"), ("🎨 Аниме-арт", "anime_art")]
    """
    return [(key, cfg["name"]) for key, cfg in PRESETS.items()]
    return [(cfg["name"], key) for key, cfg in PRESETS.items()]


def apply_preset(base_prompt: str, preset_key: str) -> dict:
    """Применяет пресет по техническому ключу"""
    preset = PRESETS.get(preset_key, {})

    return {
        "prompt": base_prompt + preset.get("prompt_suffix", ""),
        "negative_prompt": DEFAULTS["negative_prompt"] + preset.get("negative_suffix", ""),
        "width": preset.get("width", DEFAULTS["width"]),
        "height": preset.get("height", DEFAULTS["height"]),
        "steps": preset.get("steps", DEFAULTS["steps"]),
    }