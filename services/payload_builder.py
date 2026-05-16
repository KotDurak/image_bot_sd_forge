"""Сборка payload для Forge API: пресеты, VAE, override_settings."""
from typing import Optional
from models.user_state import get_user_settings
from models.users_presets import get_user_preset
import config


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
        "negative_prompt": config.DEFAULTS.get("negative_prompt", ""),
        "steps": config.DEFAULTS["steps"],
        "cfg_scale": config.DEFAULTS["cfg_scale"],
        "seed": -1,
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

    user_settings = await get_user_settings(user_id)
    user_vae = user_settings.get("vae")
    vae_to_use = "Automatic"
    if user_vae and user_vae != "None":
        vae_to_use = user_vae
    elif model_name and any(x in model_name.lower() for x in ["sdxl", "pony", "flux"]):
        vae_to_use = "sdxl_vae.safetensors"

    override = {
        "sd_vae": vae_to_use,
        "CLIP_stop_at_last_layers": 2 if (model_name and "pony" in model_name.lower()) else 1
    }
    if model_name:
        override["sd_model_checkpoint"] = model_name

    payload["override_settings"] = override
    payload["override_settings_restore_afterwards"] = True

    return payload, prompt_suffix, negative_suffix


# 🔹 Хелпер: убирает пробелы и крайние запятые
def _clean(p):
    return p.strip().strip(", ") if p else ""
