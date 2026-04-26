"""
 Команды бота: генерация, пресеты, настройки, история.
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
from services.forge_api import fetch_available_models, call_forge_api
from services.queue_manager import QueueItem
import random

logger = logging.getLogger(__name__)


# =============================================================================
# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================================================
# =============================================================================

def _apply_preset_to_payload(payload: dict, preset_cfg: dict) -> None:
    """Безопасно применяет настройки пресета к payload (in-place)"""
    payload.update({
        "width": preset_cfg.get("width", config.DEFAULTS["width"]),
        "height": preset_cfg.get("height", config.DEFAULTS["height"]),
        "steps": preset_cfg.get("steps", config.DEFAULTS["steps"]),
        "cfg_scale": preset_cfg.get("cfg_scale", config.DEFAULTS["cfg_scale"]),
        "sampler_name": preset_cfg.get("sampler", config.DEFAULTS["sampler_name"]),
        "scheduler": preset_cfg.get("scheduler", config.DEFAULTS["scheduler"]),
    })


async def _build_generation_payload(
        user_id: int,
        prompt: str,
        preset_key: Optional[str],
        model_name: Optional[str]
) -> tuple[dict, str, str]:
    """
    Собирает payload для Forge API.
    Возвращает: (payload, prompt_suffix, negative_suffix)
    """
    payload = {
        "steps": config.DEFAULTS["steps"],
        "cfg_scale": config.DEFAULTS["cfg_scale"],
        "width": config.DEFAULTS["width"],
        "height": config.DEFAULTS["height"],
        "sampler_name": config.DEFAULTS["sampler_name"],
        "batch_size": 1,
        "prompt": prompt,  # Базовый промпт
        "negative_prompt": "",
    }

    prompt_suffix = ""
    negative_suffix = ""

    if not preset_key:
        return payload, prompt_suffix, negative_suffix

    # 1. Системные пресеты
    if preset_key in config.PRESETS:
        cfg = config.PRESETS[preset_key]
        prompt_suffix = cfg.get("prompt_suffix", "")
        negative_suffix = cfg.get("negative_suffix", "")
        _apply_preset_to_payload(payload, cfg)
        logger.info(f"🎨 Системный пресет: {preset_key}")

    # 2. Кастомные пресеты из БД
    else:
        custom = await get_user_preset(user_id, preset_key)
        if custom:
            prompt_suffix = custom.get("prompt_suffix", "")
            negative_suffix = custom.get("negative_suffix", "")
            _apply_preset_to_payload(payload, custom)
            logger.info(f"🎨 Кастомный пресет: {preset_key}")
        else:
            logger.warning(f"⚠️ Пресет {preset_key} не найден")

    # Финальная сборка промптов
    payload["prompt"] = prompt + prompt_suffix
    payload["negative_prompt"] = negative_suffix

    if model_name:
        payload["model_name"] = model_name

    return payload, prompt_suffix, negative_suffix


# =============================================================================
# === КОМАНДЫ ==================================================================
# =============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветствие и главное меню"""
    user = update.effective_user
    if not user:
        return

    await update_user_settings(user.id, user.first_name, model=None, preset=None)

    keyboard = [
        [InlineKeyboardButton('🎨 Выбрать модель', callback_data="select_model")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")]
    ]

    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "🎨 Я — твой помощник для генерации картинок через Forge.\n\n"
        "📝 Просто напиши промпт, или используй команды:\n"
        "/help — команды бота\n"
        "/gen <промпт> — сгенерировать с текущими настройками\n"
        "/model — выбрать модель\n"
        "/preset — применить стиль-пресет\n\n"
        "💡 Промпты пиши на английском:\n"
        "`elegant woman, white hair, detailed eyes, soft lighting`",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def generate(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        queue_manager
) -> None:
    """Обработчик /gen — валидация, сборка задачи, отправка в очередь"""
    user = update.effective_user
    if not user:
        return
    user_id = user.id

    # 1️⃣ Проверка лимитов
    allowed, reason = await check_generation_limit(user_id)
    if not allowed:
        if reason == 'no_credits':
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🛒 Купить генерации", callback_data="buy_starter")
            ]])
            await update.message.reply_text(
                "⚠️ Лимит генераций исчерпан.\n💡 Пополните счёт, чтобы продолжить:",
                reply_markup=kb
            )
        else:
            await update.message.reply_text(reason)
        return

    # 2️⃣ Парсинг промпта
    prompt = " ".join(context.args) if context.args else update.message.text.replace("/gen", "", 1).strip()
    if not prompt:
        await update.message.reply_text(
            "❌ Укажи промпт после /gen. Пример: `/gen cyberpunk city, neon`"
        )
        return

    # 3️⃣ Сборка payload
    settings = await get_user_settings(user_id)
    payload, prompt_suffix, negative_suffix = await _build_generation_payload(
        user_id=user_id,
        prompt=prompt,
        preset_key=settings.get("preset"),
        model_name=settings.get("model")
    )
    logger.info(
        f"👤 User #{user_id}: model={settings.get('model')}, "
        f"preset={settings.get('preset')}, prompt='{prompt[:50]}...'"
    )

    # 4️⃣ Отправка в очередь
    progress_msg = await update.message.reply_text("⏳ Подключение к очереди...")

    is_free = reason in ["free", "ok"]
    # Конфиги берём из config (они в памяти, не в БД)
    show_ads = False
    if config.ADS_ENABLED:
        if config.ADS_FOR_FREE_ONLY:
            show_ads = is_free
        else:
            # Бесплатным — всегда, платным — с вероятностью
            show_ads = is_free or (random.random() < config.ADS_PAID_CHANCE)

    queue_item = QueueItem(
        user_id=user_id,
        prompt=prompt,
        payload=payload,
        message=update.message,
        progress_msg=progress_msg,
        callback=call_forge_api,
        usage_type=reason,
        preset_used=settings.get("preset"),
        show_ads=show_ads
    )

    await queue_manager.add_request(queue_item)
    await increment_usage(user_id, usage_type=reason)


async def preset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Меню управления пресетами"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Мои пресеты", callback_data="presets_list"),
            InlineKeyboardButton("➕ Создать пресет", callback_data="preset_create_start"),
        ],
        [InlineKeyboardButton("❌ Закрыть", callback_data="main_menu")]
    ]

    await update.message.reply_text(
        "🎨 **Управление пресетами**\n\n"
        "• «Создать пресет» — настрой свой стиль: промпт, негатив, размер, шаги, CFG, сэмплер\n"
        "• «Мои пресеты» — список и выбор активного",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выбор модели генерации"""
    try:
        models = fetch_available_models()
        keyboard = []

        for i in range(0, min(len(models), 20), 2):
            row = [
                InlineKeyboardButton(name, callback_data=f"model_{name}")
                for name, _ in models[i:i + 2]
            ]
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

        await update.message.reply_text(
            "🎨 Выберите модель для генерации:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в model_command: {e}", exc_info=True)
        await update.message.reply_text("❌ Не удалось загрузить модели. Проверь Forge API.")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображение текущих настроек пользователя"""
    user = update.effective_user
    if not user:
        return
    user_id = user.id

    settings = await get_user_settings(user_id)
    current_model = settings.get("model")
    current_preset_key = settings.get("preset")

    # Дефолты
    steps = config.DEFAULTS['steps']  # 🔧 FIX: было cfg_scale
    width, height = config.DEFAULTS['width'], config.DEFAULTS['height']
    cfg_scale = config.DEFAULTS['cfg_scale']
    sampler = config.DEFAULTS['sampler_name']

    # Переопределяем, если есть активный кастомный пресет
    if current_preset_key and current_preset_key not in config.PRESETS:
        user_preset = await get_user_preset(user_id, current_preset_key)
        if user_preset:
            steps = user_preset.get('steps', steps)
            width = user_preset.get('width', width)
            height = user_preset.get('height', height)
            cfg_scale = user_preset.get('cfg_scale', cfg_scale)  # 🔧 FIX: добавили
            sampler = user_preset.get('sampler', sampler)  # 🔧 FIX: добавили

    # Форматирование для вывода
    model_display = current_model.split('/')[-1] if current_model else "по умолчанию"

    preset_display = "не выбран"
    if current_preset_key:
        if current_preset_key in config.PRESETS:
            preset_display = config.PRESETS[current_preset_key].get("name", current_preset_key)
        else:
            user_preset = await get_user_preset(user_id, current_preset_key)
            if user_preset:
                preset_display = user_preset.get('name', current_preset_key)

    text = (
        "⚙️ **Ваши текущие настройки**:\n\n"
        f"🧠 Модель: `{model_display}`\n"
        f"🎨 Пресет: `{preset_display}`\n"
        f"📏 Размер: {width}×{height}\n"
        f"🔢 Шаги: {steps}\n"
        f"⚖️ CFG: {cfg_scale}\n"  # 🔧 FIX: динамическое значение
        f"🔄 Сэмплер: `{sampler}`\n\n"  # 🔧 FIX: добавили отображение
        "💡 Изменить можно через меню: /start"
    )

    keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]]

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """История генераций пользователя"""
    user = update.effective_user
    if not user:
        return

    history = await get_user_history(user.id, limit=10)

    if not history:
        await update.message.reply_text("📭 У тебя пока нет истории генераций.\nНачни с /gen!")
        return

    lines = [f"📜 **Твои последние генерации** ({len(history)}):\n"]

    for i, item in enumerate(history, 1):
        status_emoji = "✅" if item["status"] == "success" else "❌"
        model_short = item["model_used"] or "default"
        if model_short and " [" in model_short:
            model_short = model_short.split(" [")[0]

        prompt_short = (item['prompt'][:45] + "...") if len(item['prompt']) > 45 else item['prompt']

        lines.append(
            f"{i}. {status_emoji} `{prompt_short}`\n"
            f"   🎨 {model_short} | ⏱ {item['generation_time_sec'] or 0:.1f}с | 🕐 {item['created_at'][:16]}"
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")