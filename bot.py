import asyncio
import base64
import logging
import requests
from requests.auth import HTTPBasicAuth
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, \
    CallbackContext
import time
import config
from presets import apply_preset, get_preset_list

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# TODO (для продакшена лучше использовать БД/Redis)
user_settings = {}
user_last_request = {}

def get_forge_auth():
    if config.API_AUTH and len(config.API_AUTH) == 2:
        return HTTPBasicAuth(config.API_AUTH[0], config.API_AUTH[1])
    return None

def fetch_available_models():
    try:
        url = f"{config.FORGE_URL}/sdapi/v1/sd-models"
        resp = requests.get(url, auth=get_forge_auth(), timeout=30, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            models = resp.json()
            return [(m.get('model_name', m['title']), m['title']) for m in models]
    except Exception as e:
        logger.error(f"❌ Не удалось получить модели: {e}")
    # Фоллбэк на конфиг, если API не ответил
    return [(name, filename) for name, filename in config.MODELS.items()]

def call_forge_api(payload: dict) -> bytes | None :
    """Отправляет запрос к Forge API, возвращает изображение в bytes"""
    url = f"{config.FORGE_URL}/sdapi/v1/txt2img"

    if 'model_name' in payload:
        payload['override_settings'] = {"sd_model_checkpoint": payload.pop("model_name")}

    log_payload = payload.copy()
    if 'override_settings' in log_payload:
        log_payload['override_settings'] = {
            k: (v.split('/')[-1] if k == 'sd_model_checkpoint' else '***')
            for k, v in log_payload['override_settings'].items()
        }

    #  Формируем красивый лог-блок
    '''
    logger.info("🎨 === ЗАПРОС К FORGE ===")
    logger.info(f"🔗 URL: {url}")
    logger.info(f"📝 Prompt: {log_payload.get('prompt', '')}")
    logger.info(f"🚫 Negative: {log_payload.get('negative_prompt', '')}")
    logger.info(f"📏 Размер: {log_payload.get('width')}×{log_payload.get('height')}")
    logger.info(f"🔢 Шаги: {log_payload.get('steps')} | CFG: {log_payload.get('cfg_scale')}")
    logger.info(f"🎚 Сэмплер: {log_payload.get('sampler_name')}")
    logger.info(f"🧠 Модель: {log_payload.get('override_settings', {}).get('sd_model_checkpoint', 'default')}")
    logger.info(f"📦 Batch: {log_payload.get('batch_size', 1)}")
    logger.info("📦 === КОНЕЦ ЗАПРОСА ===")
    '''
    start_time = time.time()
    try:
        logger.info(f"🔗 POST {url} | prompt: {payload.get('prompt', '')[:50]}...")
        response = requests.post(
            url,
            json=payload,
            auth=get_forge_auth(),
            timeout=300,  # ⏱ 5 минут макс. (подберите под свою видеокарту)
            proxies={'http': None, 'https': None}
        )

        elapsed = time.time() - start_time
        logger.info(f"⏱ Ответ за {elapsed:.2f} сек | Статус: {response.status_code}")

        response.raise_for_status()
        result = response.json()

        if result.get("images"):
            return base64.b64decode(result["images"][0])
        logger.error("❌ В ответе нет изображений")
        return None
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут: Forge не ответил за 300 сек")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Ошибка соединения: Forge недоступен")
        return None
    except Exception as e:
        logger.error(f"❌ API error: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_settings[user_id] = {"model": None}

    keyboard = [
        [InlineKeyboardButton('🎨 Выбрать модель', callback_data="select_model")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")]
    ]

    await update.message.reply_text(
        f"👋 Привет, {update.effective_user.first_name}!\n\n"
        "🎨 Я — твой помощник для генерации картинок через Forge.\n\n"
        "📝 Просто напиши промпт, или используй команды:\n"
        "/gen <промпт> — сгенерировать с текущими настройками\n"
        "/model — выбрать модель\n"
        "/preset — применить стиль-пресет\n\n"
        "💡 промты пиши на английском:\n"
        "`elegant woman, white hair, detailed eyes, soft lighting`",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in config.ALLOWED_USERS:
        await update.message.reply_text("🔒 Доступ только для своих. Обратись к админу.")
        return

    prompt = " ".join(context.args) if context.args else update.message.text.replace("/gen", "").strip()

    if not prompt:
        await update.message.reply_text("❌ Укажи промпт после /gen. Пример: `/gen cyberpunk city, neon`")
        return

    settings = user_settings.get(user_id, {})

    model_name = settings.get("model")
    preset_key = settings.get("preset")  # 👇 Получаем ключ пресета

    prompt_suffix = ""
    negative_suffix = ""

    # 👇 Применяем пресет если выбран
    if preset_key and preset_key in config.PRESETS:
        logger.info(f"🎨 Применяю пресет: {preset_key}")
        preset_cfg = config.PRESETS[preset_key]
        prompt_suffix = preset_cfg.get("prompt_suffix", "")
        negative_suffix = preset_cfg.get("negative_suffix", "")

    logger.info(f'negative_suffix: {negative_suffix}, prompt_suffix: {prompt_suffix}')

    payload = {
        "prompt": prompt + prompt_suffix,
        "negative_prompt": config.DEFAULTS["negative_prompt"] + negative_suffix,
        "steps": config.DEFAULTS["steps"],
        "cfg_scale": config.DEFAULTS["cfg_scale"],
        "width": config.DEFAULTS["width"],
        "height": config.DEFAULTS["height"],
        "sampler_name": config.DEFAULTS["sampler"],
        "batch_size": 1,
    }

    if model_name:
        payload["model_name"] = model_name
        await update.message.reply_text(f"🔄 Генерирую с моделью: `{model_name.split('/')[-1]}`...",
                                        parse_mode="Markdown")
    else:
        await update.message.reply_text("🔄 Генерирую с моделью по умолчанию...")

    # 👇 Добавим лог для отладки
    logger.info(f"👤 User #{user_id}: model={model_name}, preset={preset_key}, prompt='{prompt[:50]}...'")
    logger.info(payload)
    progress_msg = await update.message.reply_text("⏳ Загрузка модели и подготовка...")

    image_bytes = await asyncio.to_thread(call_forge_api, payload)

    if image_bytes:
        await progress_msg.delete()
        caption = f"✅ Готово!\n📝 `{prompt[:100]}{'...' if len(prompt) > 100 else ''}`"
        if model_name:
            caption += f"\n🧠 Модель: `{model_name.split('/')[-1]}`"
        await update.message.reply_photo(photo=image_bytes, caption=caption, parse_mode="Markdown")
    else:
        await progress_msg.edit_text("❌ Ошибка генерации. Проверь логи.")

async def select_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора модели через inline-кнопки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    # Если нажали на конкретную модель

    if query.data.startswith("model_"):
        model_title = query.data.replace("model_", "")
        models = fetch_available_models()
        for display_name, full_name in models:
            if display_name == model_title:
                user_settings.setdefault(user_id, {})["model"] = full_name
                await query.edit_message_text(
                    f"✅ Выбрана модель:\n`{full_name.split('/')[-1]}`\n\n"
                    "Теперь используй /gen для генерации.",
                    parse_mode="Markdown"
                )
                return
    models = fetch_available_models()
    keyboard = []

    for i in range(0, min(len(models), 20), 2):  # лимит 20 для удобства
        row = [InlineKeyboardButton(name, callback_data=f"model_{name}") for name, _ in models[i:i + 2]]
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

    await query.edit_message_text(
        "🎨 Выберите модель для генерации:\n"
        "(первые 20 из доступных)",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def presets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает пресеты стилей"""
    query = update.callback_query
    await query.answer()
    logger.info('presets callback called')
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"preset_{key}")]
        for key, name in get_preset_list()
    ]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

    await query.edit_message_text(
        "🎨 Выберите стиль-пресет:\n"
        "Он автоматически добавит подходящие слова к промпту и настроит параметры.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def preset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовой команды /preset"""
    try:
        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"preset_{key}")]
            for key, name in get_preset_list()
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

        # 👇 Текст явно в одной строке — никаких переносов внутри reply_text!
        await update.message.reply_text(
            "🎨 Выберите стиль-пресет:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в preset_command: {e}")
        await update.message.reply_text("❌ Не удалось загрузить пресеты. Попробуйте позже.")


async def apply_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Применяет выбранный пресет"""
    query = update.callback_query
    await query.answer()

    # Извлекаем ТЕХНИЧЕСКИЙ ключ: "preset_portrait" → "portrait"
    preset_key = query.data.replace("preset_", "")

    # Получаем конфиг пресета
    preset_config = config.PRESETS.get(preset_key, {})

    # Красивое имя для отображения
    preset_name = preset_config.get("name", preset_key)

    # Сохраняем в настройках пользователя
    user_settings.setdefault(query.from_user.id, {})["preset"] = preset_key

    await query.edit_message_text(
        f"✅ Применён пресет: **{preset_name}**\n\n"
        "Теперь напиши промпт после /gen — пресет автоматически добавит нужные детали!\n"
        "Пример: `/gen woman with white hair`",
        parse_mode="Markdown"
    )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /model — показывает кнопки выбора модели"""
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

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущие настройки и позволяет изменить базовые параметры"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    settings = user_settings.get(user_id, {})

    # Формируем текст с настройками
    current_model = settings.get("model", "по умолчанию")
    text = (
        "⚙️ **Ваши настройки**:\n\n"
        f"🧠 Модель: `{current_model.split('/')[-1] if current_model else 'дефолт'}`\n"
        f"📏 Размер: {config.DEFAULTS['width']}×{config.DEFAULTS['height']}\n"
        f"🔢 Шаги: {config.DEFAULTS['steps']}\n"
        f"⚖️ CFG: {config.DEFAULTS['cfg_scale']}\n\n"
    )

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Возврат в главное меню"""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("🎨 Выбрать модель", callback_data="select_model")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")],
    ]

    await query.edit_message_text(
        "🎛 Главное меню:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка по командам"""
    await update.message.reply_text(
        "📚 **Команды бота**:\n\n"
        "/start — начать работу, показать меню\n"
        "/gen <промпт> — сгенерировать изображение\n"
        "/model — открыть выбор моделей\n"
        "/preset — применить стиль-пресет\n"
        "/help — эта справка\n\n"
        "💡 **Советы для новичка**:\n"
        "• Пиши промпты на английском — результаты лучше\n"
        "• Начинай с простого: `woman, white hair, elegant`\n"
        "• Добавляй детали постепенно: `+ detailed eyes + soft lighting`\n"
        "• Используй пресеты для быстрого старта",
        parse_mode="Markdown"
    )


# ===== ЗАПУСК =====

def main():
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("gen", generate))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("preset", preset_command))
    app.add_handler(CommandHandler("model", model_command))

    # Callbacks для inline-кнопок
    app.add_handler(CallbackQueryHandler(select_model_callback, pattern="^select_model$|^model_"))
    app.add_handler(CallbackQueryHandler(presets_callback, pattern="^presets$"))
    app.add_handler(CallbackQueryHandler(apply_preset_callback, pattern="^preset_"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))

    logger.info("🤖 Бот запущен и готов к творчеству!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    restart_count = 0

    while True:
        try:
            main()
            restart_count = 0  # сброс если вдруг нормально вышел
        except Exception as e:
            restart_count += 1
            logger.error(f"🔥 Краш #{restart_count}: {e}", exc_info=True)

            if restart_count > 5:
                logger.critical("💀 Слишком много падений. Ждём 60 сек...")
                time.sleep(60)
            else:
                time.sleep(5)