import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.queue_manager import QueueItem
from services.forge_api import fetch_available_models, call_forge_api
from models.user_state import get_user_settings, update_user_settings
import config
from models.users_presets import get_user_preset

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    update_user_settings(user_id, update.effective_user.first_name, model=None, preset=None)

    keyboard = [
        [InlineKeyboardButton('🎨 Выбрать модель', callback_data="select_model")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")]
    ]

    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        "🎨 Я — твой помощник для генерации картинок через Forge.\n\n"
        "📝 Просто напиши промпт, или используй команды:\n"
        "/help команды бота\n"
        "/gen <промпт> — сгенерировать с текущими настройками\n"
        "/model — выбрать модель\n"
        "/preset — применить стиль-пресет\n\n"
        "💡 промты пиши на английском:\n"
        "`elegant woman, white hair, detailed eyes, soft lighting`",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_manager):
    """Обработчик /gen — добавляет запрос в очередь"""
    user_id = update.effective_user.id
    from models.user_quota import check_generation_limit, increment_usage

    allowed, reason = check_generation_limit(user_id)

    if not allowed:
        await update.message.reply_text(reason)
        return

    #TODO Настроить более адекватную проверку на доступы (через бд)
    ''' if user_id not in config.ALLOWED_USERS:
        await update.message.reply_text("🔒 Доступ только для своих. Обратись к админу.")
        return 
    '''
    prompt = " ".join(context.args) if context.args else update.message.text.replace("/gen", "").strip()

    if not prompt:
        await update.message.reply_text("❌ Укажи промпт после /gen. Пример: `/gen cyberpunk city, neon`")
        return

    settings = get_user_settings(user_id)
    model_name = settings.get("model")
    preset_key = settings.get("preset")

    prompt_suffix = ""
    negative_suffix = ""
    payload = {
        "steps": config.DEFAULTS["steps"],
        "cfg_scale": config.DEFAULTS["cfg_scale"],
        "width": config.DEFAULTS["width"],
        "height": config.DEFAULTS["height"],
        "sampler_name": config.DEFAULTS["sampler"],
        "batch_size": 1,
    }

    if preset_key and preset_key in config.PRESETS:
        # Системный пресет
        cfg = config.PRESETS[preset_key]
        prompt_suffix = cfg.get("prompt_suffix", "")
        negative_suffix = cfg.get("negative_suffix", "")
        payload["width"] = cfg.get("width", 512)
        payload["height"] = cfg.get("height", 512)
        payload["steps"] = cfg.get("steps", 20)
        logger.info(f"🎨 Системный пресет: {preset_key}")
    elif preset_key:
        # Кастомный пресет из БД
        from models.users_presets import get_user_preset
        custom = get_user_preset(user_id, preset_key)
        if custom:
            prompt_suffix = custom.get("prompt_suffix", "")
            negative_suffix = custom.get("negative_suffix", "")
            payload["width"] = custom.get("width", 512)
            payload["height"] = custom.get("height", 512)
            payload["steps"] = custom.get("steps", 20)
            logger.info(f"🎨 Кастомный пресет: {preset_key}")
        else:
            logger.warning(f"⚠️ Пресет {preset_key} не найден ни в системе, ни в БД")

    payload["prompt"] = prompt + prompt_suffix
    payload["negative_prompt"] = negative_suffix
    if model_name:
        payload["model_name"] = model_name

    logger.info(f"👤 User #{user_id}: model={model_name}, preset={preset_key}, prompt='{prompt[:50]}...'")

    progress_msg = await update.message.reply_text("⏳ Подключение к очереди...")

    queue_item = QueueItem(
        user_id=user_id,
        prompt=prompt,
        payload=payload,
        message=update.message,
        progress_msg=progress_msg,
        callback=call_forge_api
    )

    await queue_manager.add_request(queue_item)
    increment_usage(user_id)


async def preset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовой команды /preset"""
    """/preset — меню управления пресетами"""
    keyboard = [
        [
            InlineKeyboardButton("📋 Мои пресеты", callback_data="presets_list"),
            InlineKeyboardButton("➕ Создать пресет", callback_data="preset_create_start"),
        ],
        [InlineKeyboardButton("❌ Закрыть", callback_data="main_menu")]
    ]

    await update.message.reply_text(
        "🎨 **Управление пресетами**\n\n"
        "• «Создать пресет» — настрой свой стиль: промпт, негатив, размер, шаги\n"
        "• «Мои пресеты» — список и выбор активного",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /model — показывает кнопки выбора модели"""
    try:
        models = fetch_available_models()
        keyboard = []

        for i in range(0, min(len(models), 20), 2):
            row = [InlineKeyboardButton(name, callback_data=f"model_{name}") for name, _ in models[i:i + 2]]
            keyboard.append(row)

        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

        await update.message.reply_text(
            "🎨 Выберите модель для генерации:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в model_command: {e}")
        await update.message.reply_text("❌ Не удалось загрузить модели. Проверь Forge API.")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /settings — показывает текущие настройки"""
    user_id = update.effective_user.id
    settings = get_user_settings(int(user_id))
    print(settings)
    current_model = settings.get("model")
    current_preset = settings.get("preset")

    steps = config.DEFAULTS['cfg_scale']
    width, height = config.DEFAULTS['width'], config.DEFAULTS['height']
    user_preset =  get_user_preset(user_id, current_preset) if current_preset else None
    # Получаем красивые названия
    model_display = current_model.split('/')[-1] if current_model else "по умолчанию"


    preset_display = "не выбран"
    if current_preset and current_preset in config.PRESETS:
        preset_display = config.PRESETS[current_preset].get("name", current_preset)
    elif user_preset:
        preset_display = user_preset.get('name')
        steps = user_preset.get('steps')
        width,height = user_preset.get('width'), user_preset.get('height')

    text = (
        "⚙️ **Ваши текущие настройки**:\n\n"
        f"🧠 Модель: `{model_display}`\n"
        f"🎨 Пресет: `{preset_display}`\n"
        f"📏 Размер: {width}×{height}\n"
        f"🔢 Шаги: {steps}\n"
        f"⚖️ CFG: {config.DEFAULTS['cfg_scale']}\n\n"
        "💡 Изменить можно через меню: /start"
    )

    keyboard = [[InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")]]

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))