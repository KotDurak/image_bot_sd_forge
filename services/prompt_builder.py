from typing import Tuple, Union
import logging

logger = logging.getLogger(__name__)


SYSTEM_PRESETS = {
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

# Глобальные фильтры для бизнес-режима
BUSINESS_NEGATIVE = (
    ", nsfw, nude, naked, explicit, sexual, porn, underwear, cleavage, "
    "bikini, lingerie, bare chest, topless, bottomless"
)

def build_final_prompt(
    user_prompt: str,
    preset: Union[dict, None],
    is_business_safe: bool = False
) -> Tuple[str, str]:
    """
    Собирает финальный промпт и негатив.
    Возвращает (prompt, negative_prompt).
    """

    # Базовые суффиксы
    prompt_suffix = preset.get('prompt_suffix', '') if preset else ''
    negative_suffix = preset.get('negative_suffix', '') if preset else ''

    if is_business_safe:
        negative_suffix = f"{negative_suffix}{BUSINESS_NEGATIVE}".strip()

    suspicious = ['nude', 'naked', 'porn', 'xxx', 'bare', 'lingerie', 'underwear']
    if is_business_safe and any(kw in user_prompt.lower() for kw in suspicious):
        logger.warning(f"🔒 Запрос содержит подозрительные слова, усилены фильтры")
        negative_suffix += ", nsfw, explicit"

    final_prompt = f"{user_prompt} {prompt_suffix}".strip()
    final_negative = negative_suffix.strip()

    return final_prompt, final_negative