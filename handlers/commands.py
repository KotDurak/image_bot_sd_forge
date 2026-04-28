"""
Команды бота: генерация, пресеты, настройки, история.
Архитектура: payload собирается ЗДЕСЬ и передаётся дальше БЕЗ ИЗМЕНЕНИЙ.
"""
import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from models.generation_log import get_user_history
from models.user_quota import check_generation_limit, increment_usage
from models.user_state import get_user_settings, update_user_settings
from models.users_presets import get_user_preset
from services.forge_api import fetch_available_models, fetch_available_vae, call_forge_api
from services.queue_manager import QueueItem
import random
import re
from utils.translate import translate_prompt_free
logger = logging.getLogger(__name__)
CYRILLIC_RE = re.compile(r'[а-яА-ЯёЁ]')

# =============================================================================
# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================================================
# =============================================================================

def _apply_preset_to_payload(payload: dict, preset_cfg: dict) -> None:
    payload.update({
        "width": preset_cfg.get("width", payload["width"]),
        "height": preset_cfg.get("height", payload["height"]),
        "steps": preset_cfg.get("steps", payload["steps"]),
        "cfg_scale": preset_cfg.get("cfg_scale", payload["cfg_scale"]),
        "sampler_name": preset_cfg.get("sampler", payload["sampler_name"]),
        "scheduler": preset_cfg.get("scheduler", payload.get("scheduler", "karras")),
    })


async def _build_generation_payload(
    user_id: int,
    prompt: str,
    preset_key: Optional[str],
    model_name: Optional[str]
) -> tuple[dict, str, str]:
    # 1. Базовая структура (строго по валидному JSON)
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

    prompt_prefix, prompt_suffix, negative_suffix = "", "", ""

    # 2. Применяем пресет (если выбран)
    if preset_key:
        cfg = config.PRESETS.get(preset_key)
        if not cfg:
            cfg = await get_user_preset(user_id, preset_key)

        if cfg:
            _apply_preset_to_payload(payload, cfg)
            prompt_prefix = cfg.get("prompt_prefix", "")
            prompt_suffix = cfg.get("prompt_suffix", "")
            negative_suffix = cfg.get("negative_suffix", "")

    # 3. Собираем финальный промпт: ПРЕФИКС + ВВОД ПОЛЬЗОВАТЕЛЯ + СУФФИКС
    # Фильтруем пустые строки, склеиваем пробелом, убираем лишние пробелы
    parts = [p.strip() for p in (prompt_prefix, prompt, prompt_suffix) if p]
    payload["prompt"] = " ".join(parts)
    if negative_suffix:
        payload["negative_prompt"] = negative_suffix

    # 4. Резолв VAE
    user_settings = await get_user_settings(user_id)
    user_vae = user_settings.get("vae")
    vae_to_use = "Automatic"
    if user_vae and user_vae != "None":
        vae_to_use = user_vae
    elif model_name and any(x in model_name.lower() for x in ["sdxl", "pony", "flux"]):
        vae_to_use = "sdxl_vae.safetensors"

    # 5. Формируем override_settings ТОЛЬКО здесь
    override = {
        "sd_vae": vae_to_use,
        "CLIP_stop_at_last_layers": 2 if (model_name and "pony" in model_name.lower()) else 1
    }
    if model_name:
        override["sd_model_checkpoint"] = model_name

    payload["override_settings"] = override
    payload["override_settings_restore_afterwards"] = True

    return payload, prompt_suffix, negative_suffix


# =============================================================================
# === КОМАНДЫ ==================================================================
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return
    await update_user_settings(user.id, user.first_name, model=None, preset=None)

    keyboard = [
        [InlineKeyboardButton('🎨 Выбрать модель', callback_data="select_model")],
        [InlineKeyboardButton('🔧 Выбрать VAE', callback_data="select_vae")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")]
    ]
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "🎨 Я — твой помощник для генерации картинок через Forge.\n\n"
        "📝 Напиши промпт или используй команды:\n"
        "/gen <промпт> — сгенерировать\n"
        "/model — модель | /vae — декодер | /preset — стиль",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_manager) -> None:
    user = update.effective_user
    if not user: return
    user_id = user.id

    allowed, reason = await check_generation_limit(user_id)
    if not allowed:
        if reason == 'no_credits':
            await update.message.reply_text(
                "⚠️ Лимит исчерпан. Пополни счёт или подожди обновления.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🛒 Пополнить", callback_data="buy_starter")
                ]])
            )
        else:
            await update.message.reply_text(reason)
        return

    prompt = " ".join(context.args) if context.args else update.message.text.replace("/gen", "", 1).strip()
    if not prompt:
        await update.message.reply_text("❌ Укажи промпт. Пример: `/gen cyberpunk city`")
        return

    if CYRILLIC_RE.search(prompt):
        # 🌐 Пробуем бесплатный облачный перевод
        prompt = await translate_prompt_free(prompt)
        # Если кириллица осталась (API выкл, упал, превышен лимит или не справился)
        if CYRILLIC_RE.search(prompt):
            await update.message.reply_text(
                "🇷🇺 Нейросети не понимают русский. Переведи промпт на английский (Google, DeepL, Яндекс)\n"
                "💡 Пример: `cat stealing ham, cinematic lighting, photorealistic`",
                parse_mode="Markdown"
            )
            return

    settings = await get_user_settings(user_id)
    active_model = settings.get("model") or config.DEFAULT_MODEL

    payload, _, _ = await _build_generation_payload(
        user_id=user_id,
        prompt=prompt,
        preset_key=settings.get("preset"),
        model_name=active_model
    )

    progress_msg = await update.message.reply_text("⏳ Подключение к очереди...")
    is_free = reason in ["free", "ok"]
    show_ads = config.ADS_ENABLED and (is_free or (not is_free and random.random() < config.ADS_PAID_CHANCE))

    queue_item = QueueItem(
        user_id=user_id, prompt=prompt, payload=payload,
        message=update.message, progress_msg=progress_msg,
        callback=call_forge_api, usage_type=reason,
        preset_used=settings.get("preset"), show_ads=show_ads
    )
    await queue_manager.add_request(queue_item)
    await increment_usage(user_id, usage_type=reason)


# ... (preset_command, model_command, vae_command, settings_command, history_cmd остаются без изменений)
# Для экономии места оставляю их как в твоём коде. Главное — _build_generation_payload теперь правильный.
async def preset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[
        InlineKeyboardButton("📋 Мои пресеты", callback_data="presets_list"),
        InlineKeyboardButton("➕ Создать пресет", callback_data="preset_create_start"),
    ], [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
    await update.message.reply_text("🎨 Управление пресетами", reply_markup=InlineKeyboardMarkup(keyboard))


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        models = fetch_available_models()
        kb = [InlineKeyboardButton(n, callback_data=f"model_{n}") for n, _ in models[:20]]
        rows = [kb[i:i + 2] for i in range(0, len(kb), 2)] + [
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        await update.message.reply_text("🎨 Выберите модель:", reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        logger.error(f"model_command error: {e}")
        await update.message.reply_text("❌ Ошибка загрузки моделей.")


async def vae_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        vae_list = fetch_available_vae()
        kb = [InlineKeyboardButton(n, callback_data=f"vae_{f}") for n, f in vae_list]
        rows = [kb[i:i + 2] for i in range(0, len(kb), 2)]
        rows += [[InlineKeyboardButton("🔄 Сбросить (Авто)", callback_data="vae_null"),
                  InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        settings = await get_user_settings(update.effective_user.id)
        cur = settings.get("vae") or "Автоподбор"
        await update.message.reply_text(
            f"🔧 Выбор VAE (текущий: <code>{cur}</code>)\n\n"
            "• Automatic — встроенный в модель (рекомендуется)\n"
            "• Файлы — явная замена при артефактах",
            reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text("❌ Ошибка загрузки списка VAE.")


async def cb_vae_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    vae_val = q.data[4:] if q.data != "vae_null" else None
    await update_user_settings(q.from_user.id, username=None, vae=vae_val)
    await q.edit_message_text(
        f"✅ VAE {'сброшен' if vae_val is None else 'установлен'}: <code>{vae_val or 'Авто'}</code>", parse_mode="HTML")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user: return
    s = await get_user_settings(user.id)
    p = await get_user_preset(user.id, s["preset"]) if s["preset"] and s["preset"] not in config.PRESETS else None
    w = p.get("width", config.DEFAULTS["width"]) if p else config.DEFAULTS["width"]
    h = p.get("height", config.DEFAULTS["height"]) if p else config.DEFAULTS["height"]
    steps = p.get("steps", config.DEFAULTS["steps"]) if p else config.DEFAULTS["steps"]
    cfg = p.get("cfg_scale", config.DEFAULTS["cfg_scale"]) if p else config.DEFAULTS["cfg_scale"]
    samp = p.get("sampler", config.DEFAULTS["sampler_name"]) if p else config.DEFAULTS["sampler_name"]

    txt = (
        f"⚙️ Настройки:\n🧠 Модель: `{s['model'] or 'default'}`\n"
        f"🎨 Пресет: `{s['preset'] or 'none'}`\n🔧 VAE: `{s['vae'] or 'Авто'}`\n"
        f"📏 {w}×{h} | 🔢 {steps} шагов | ⚖️ CFG {cfg} | 🔄 {samp}"
    )
    await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")
    ]]))


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user: return
    hist = await get_user_history(user.id, limit=10)
    if not hist:
        await update.message.reply_text("📭 История пуста.")
        return
    lines = [f"📜 Последние генерации:\n"]
    for i, h in enumerate(hist, 1):
        st = "✅" if h["status"] == "success" else "❌"
        pr = h['prompt'][:40] + "..." if len(h['prompt']) > 40 else h['prompt']
        lines.append(f"{i}. {st} `{pr}` | ⏱ {h['generation_time_sec']:.1f}с")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")