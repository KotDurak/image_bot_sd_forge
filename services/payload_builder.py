"""Сборка payload для Forge API: пресеты, VAE, override_settings."""
from typing import Optional
from models.user_state import get_user_settings
from models.users_presets import get_user_preset
import config
import re

HUMAN_TRIGGERS = re.compile(
    r'\b(girl|boy|man|woman|solo|1girl|1boy|waifu|hands?|fingers?|holding|character|person|female|male|lady|guy)\b',
    re.IGNORECASE
)

def apply_preset_to_payload(payload: dict, preset_cfg: dict) -> None:
    """Применяет параметры пресета к payload."""
    payload.update({
        "width": preset_cfg.get("width", payload["width"]),
        "height": preset_cfg.get("height", payload["height"]),
        "steps": preset_cfg.get("steps", payload["steps"]),
        "cfg_scale": preset_cfg.get("cfg_scale", payload["cfg_scale"]),
        "sampler_name": preset_cfg.get("sampler", payload["sampler_name"]),
        "scheduler": preset_cfg.get("scheduler", payload.get("scheduler", "karras")),
    })


async def build_generation_payload(
        user_id: int,
        prompt: str,
        preset_key: Optional[str],
        model_name: Optional[str],
        lora_string: Optional[str] = None
) -> tuple[dict, str, str]:
    """
    Собирает полный payload для генерации.
    Возвращает (payload, prompt_suffix, negative_suffix).
    """
    payload = {
        "prompt": prompt,
        "negative_prompt": config.DEFAULTS.get("negative_suffix", ""),
        "steps": config.DEFAULTS["steps"],
        "cfg_scale": config.DEFAULTS["cfg_scale"],
        "seed": config.SEED,
        "width": config.DEFAULTS["width"],
        "height": config.DEFAULTS["height"],
        "sampler_name": config.DEFAULTS["sampler_name"],
        "scheduler": config.DEFAULTS.get("scheduler", "karras"),
        "batch_size": 1,
        "n_iter": 1,
        "restore_faces": False,
        "tiling": False,
        "do_not_save_samples": True,
        "do_not_save_grid": True,
    }

    prompt_prefix = config.DEFAULTS.get('prompt_prefix', "")
    prompt_suffix = config.DEFAULTS.get('prompt_suffix', "")
    negative_suffix = config.DEFAULTS.get('negative_suffix', "")

    if preset_key:
        cfg = config.PRESETS.get(preset_key)
        if not cfg:
            cfg = await get_user_preset(user_id, preset_key)

        if cfg:
            apply_preset_to_payload(payload, cfg)
            prompt_prefix = cfg.get("prompt_prefix", "")
            prompt_suffix = cfg.get("prompt_suffix", "")
            negative_suffix = cfg.get("negative_suffix", "")
    prompt_prefix, negative_suffix = add_handfixers_to_prompt(prompt_prefix,
                                                              negative_suffix,
                                                              prompt,
                                                              model_name,
                                                              preset_key)

    parts = [p for p in (_clean(prompt_prefix), _clean(prompt), _clean(prompt_suffix)) if p]

    # 2. Добавляем LoRA (тоже чистим)
    if lora_string:
        lora_clean = _clean(lora_string)
        if lora_clean:
            parts.append(lora_clean)

    # 3. Склеиваем через запятую + пробел (стандарт SD/A1111)
    payload["prompt"] = ", ".join(parts)
    if negative_suffix:
        payload["negative_prompt"] = negative_suffix

    if config.ENABLE_ADETAILER and model_name and any(x in model_name.lower() for x in ["pony", "animagine"]):
        payload["alwayson_scripts"] = {
            "ADetailer": {"args": get_adetailer_args_dict(payload['prompt'])}
        }
        
    user_settings = await get_user_settings(user_id)
    user_vae = user_settings.get("vae")
    vae_to_use = "Automatic"
    if user_vae and user_vae != "None":
        vae_to_use = user_vae
    elif model_name and any(x in model_name.lower() for x in ["sdxl", "pony", "flux"]):
        '''
        vae_to_use = "sdxl_vae.safetensors"
        '''

    override = {
        "sd_vae": vae_to_use,
        "CLIP_stop_at_last_layers": 2 if (model_name and any(x in model_name.lower() for x in ["autismmix", "pony"])) else 1
    }
    if model_name:
        override["sd_model_checkpoint"] = model_name

    payload["override_settings"] = override
    payload["override_settings_restore_afterwards"] = True

    return payload, prompt_suffix, negative_suffix


# 🔹 Хелпер: убирает пробелы и крайние запятые
def _clean(p):
    return p.strip().strip(", ") if p else ""


def get_adetailer_args_dict(user_prompt: str) -> list:
    """
    Возвращает строго валидный конфиг для ADetailer API.
    Проходит Pydantic-валидацию в ADetailer v24+.
    """
    user_prompt_lower = user_prompt.lower()
    human_triggers = [
        "girl", "boy", "man", "woman", "solo", "1girl", "1boy",
        "waifu", "hands", "finger", "holding", "character"
    ]

    # Включаем ADetailer только для людей/персонажей
    if not any(trigger in user_prompt_lower for trigger in human_triggers):
        return [False]  # или [] в зависимости от твоего API-враппера

    # 🔧 ПОЛНОСТЬЮ ВАЛИДНЫЙ СЛОВАРЬ ПО СХЕМЕ ADETAILER API
    valid_adetailer_hand_cfg = {
        "ad_model": "hand_yolov8n.pt",
        "ad_prompt": "score_9, score_8_up, perfect hands, detailed fingers, <lora:HandFixer_pdxl_Incrs_v1:0.6>",
        "ad_negative_prompt": "score_3, score_4, score_5, bad anatomy, mutated hands, extra digits",
        "ad_confidence": 0.3,
        "ad_mask_blur": 4,
        "ad_denoising_strength": 0.4,
        "ad_inpaint_width": 256,
        "ad_inpaint_height": 256
    }

    # Возвращай строго так:
    return [valid_adetailer_hand_cfg]



def add_handfixers_to_prompt(prompt_prefix: str, negative_suffix: str, prompt: str, model_name: str, preset_key: str):
    clean_model = model_name.split(" [")[0].strip()
    fixer = config.HAND_FIXERS.get(clean_model)
    if not fixer:
        return prompt_prefix, negative_suffix

    hands_str = fixer.get('hands_str', '')
    hands_neg = fixer.get('hands_negative', '')
    preset_allowed = fixer.get('preset_key')

    # Нормализуем в список, чтобы код работал и если в конфиге лежит одна строка, а не список
    if isinstance(preset_allowed, str):
        preset_allowed = [preset_allowed]

    # 🔑 ИСПРАВЛЕНИЕ:
    # Пропускаем авто-фиксатор ТОЛЬКО если пользователь явно выбрал пресет,
    # которого НЕТ в списке разрешённых для данной модели.
    # Если preset_key пустой/None -> применяем.
    # Если preset_key есть и совпадает с одним из списка -> применяем.
    if preset_key and preset_allowed and preset_key not in preset_allowed:
        return prompt_prefix, negative_suffix

    if not HUMAN_TRIGGERS.search(prompt):
        return prompt_prefix, negative_suffix

    if hands_str.strip() and hands_str.strip() not in prompt_prefix:
        prompt_prefix += hands_str
    if hands_neg.strip() and hands_neg.strip() not in negative_suffix:
        negative_suffix += hands_neg

    return prompt_prefix, negative_suffix