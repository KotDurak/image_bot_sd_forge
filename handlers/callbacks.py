import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from models.user_state import get_user_settings, update_user_settings
from presets import get_preset_list
import config
from models.users_presets import get_user_preset
from services.forge_api import fetch_available_models

logger = logging.getLogger(__name__)

async def select_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data.startswith("model_"):
        model_title = query.data.replace("model_", "")
        models = fetch_available_models()
        for display_name, full_name in models:
            if display_name == model_title:
                await update_user_settings(user_id, query.from_user.username, model=full_name)
                await query.edit_message_text(
                    f"✅ Выбрана модель:\n`{full_name.split('/')[-1]}`\n\n"
                    "Теперь используй /gen для генерации.",
                    parse_mode="Markdown"
                )
                return
    models = fetch_available_models()
    keyboard = []
    for i in range(0, min(len(models), 20), 2):
        row = [InlineKeyboardButton(name, callback_data=f"model_{name}") for name, _ in models[i:i + 2]]
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

    await query.edit_message_text(
        "🎨 Выберите модель для генерации:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def presets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"preset_{key}")]
        for key, name in get_preset_list()
    ]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    await query.edit_message_text(
        "🎨 Выберите стиль-пресет:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def apply_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    preset_key = query.data.replace("preset_", "")
    preset_config = config.PRESETS.get(preset_key, {})
    preset_name = preset_config.get("name", preset_key)
    await update_user_settings(query.from_user.id, query.from_user.username, preset=preset_key)
    await query.edit_message_text(
        f"✅ Применён пресет: **{preset_name}**\n\n"
        "Теперь напиши промпт после /gen — пресет автоматически добавит нужные детали!",
        parse_mode="Markdown"
    )


# handlers/callbacks.py
async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает текущие настройки через inline-кнопки (с учётом sampler/scheduler)"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    settings = await get_user_settings(user_id)

    # 🔹 Дефолты
    width = config.DEFAULTS['width']
    height = config.DEFAULTS['height']
    steps = config.DEFAULTS['steps']
    cfg_scale = config.DEFAULTS['cfg_scale']
    sampler_name = config.DEFAULTS.get('sampler_name', 'Euler')
    scheduler = config.DEFAULTS.get('scheduler', 'automatic')

    current_model = settings.get("model")
    current_preset = settings.get("preset")

    # 🔹 Если есть активный кастомный пресет — переопределяем дефолты
    if current_preset and current_preset not in config.PRESETS:
        user_preset = await get_user_preset(user_id, current_preset)
        if user_preset:
            width = user_preset.get('width', width)
            height = user_preset.get('height', height)
            steps = user_preset.get('steps', steps)
            cfg_scale = user_preset.get('cfg_scale', cfg_scale)
            sampler_name = user_preset.get('sampler_name', sampler_name)
            scheduler = user_preset.get('scheduler', scheduler)

    # 🔹 Форматирование для вывода
    model_display = current_model.split('/')[-1].split('[')[0].strip() if current_model else "по умолчанию"

    preset_display = "не выбран"
    if current_preset:
        if current_preset in config.PRESETS:
            preset_display = config.PRESETS[current_preset].get("name", current_preset)
        else:
            user_preset = await get_user_preset(user_id, current_preset)
            if user_preset:
                preset_display = user_preset.get('name', current_preset)

    # 🔹 Текст с настройками
    text = (
        "⚙️ **Ваши текущие настройки**:\n\n"
        f"🧠 Модель: `{model_display}`\n"
        f"🎨 Пресет: `{preset_display}`\n"
        f"📏 Размер: `{width}×{height}`\n"
        f"🔢 Шаги: `{steps}`\n"
        f"⚖️ CFG: `{cfg_scale}`\n"
        f"🔄 Сэмплер: `{sampler_name}`\n"
        f"📅 Scheduler: `{scheduler}`\n\n"
        "💡 Изменить: /preset или /start"
    )

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🎨 Выбрать модель", callback_data="select_model")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")],
    ]
    await query.edit_message_text("🎛 Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))



async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Умная справка: показывает команды в зависимости от роли пользователя"""
    user_id = update.effective_user.id
    is_admin = user_id in config.ADMINS
    msg = update.effective_message or update.message  # 🔒 Защита от NoneType

    # 🎨 Базовые команды (видят все)
    text = (
        "📚 **Справка по боту**\n\n"
        "🎨 **Генерация:**\n"
        "`/gen <промпт>` — создать изображение (писать на английском)\n"
        "`/model` — выбрать нейросеть (модель)\n"
        "`/vae` — выбрать декодер (решает проблемы с цветами/мылом)\n"
        "`/preset` — меню пресетов: применить или создать через визард\n"
        "`/preset_add` — 🚀 быстрое создание пресета в одну строку:\n"
        "`/preset_add name=PonyV6 key=pony prefix=score_9, score_8_up, res=832x1216 steps=28 sampler=DPM++ 2M scheduler=karras prompt=masterpiece negative=bad hands`\n"
        "`/settings` — текущие параметры генерации (CFG, sampler, размер)\n"
        "`/cancel` — отменить мастер пресетов или зависшую задачу\n"
        "`/start` — сбросить настройки пользователя (если застрял)\n"
        "\n"
        "🔍 **Справка по опциям:**\n"
        "`/samplers` — показать доступные сэмплеры из Forge 🔄\n"
        "`/schedulers` — показать доступные шедулеры из Forge 📅\n"
        "\n"
        "💳 **Баланс и оплата:**\n"
        "`/balance` — проверить количество доступных генераций\n"
        "`/buy` — купить пакет генераций за Telegram Stars ⭐\n"
        "\n"
        "📜 **История и поддержка:**\n"
        "`/history` — твои последние 10 генераций\n"
        "`/report` — если кредиты списались, но картинка не пришла\n"
        "\n"
        "💡 **Советы:**\n"
        "• *Пиши промпты на английском (важно)*\n"
        "• Для Pony V6 обязательно используй `prefix=score_9, score_8_up, score_7_up,`\n"
        "• Размеры должны быть кратны 8 (например, 832×1216)\n"
        "• Реклама показывается после генерации — можно пропустить"
    )

    # 🔐 Админские команды (видят только админы)
    if is_admin:
        text += (
            "\n\n"
            "🔐 **Админ-панель**:\n"
            "`/ad_report <id> [стр]` — детальный отчёт по рекламной кампании 📊\n"
            "`/ad_template` — получить шаблон CSV для загрузки рекламы 📥\n"
            "`/refresh_forge` — обновить кеш сэмплеров/шедулеров из Forge 🔄\n"
            "*(Отправь заполненный .csv/.json файл — бот импортирует рекламу)*\n"
            "\n"
            "⚙️ **Отладка**:\n"
            "`/unlimited <user_id>` — дать безлимитные генерации (тест)\n"
            "`/ban <user_id>` — заблокировать пользователя\n"
            "`/reset <user_id>` — сбросить лимиты пользователя\n"
        )

    # 🎛 Кнопки быстрого доступа
    keyboard = [
        [InlineKeyboardButton("🎨 Выбрать модель", callback_data="select_model")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
    ]

    if is_admin:
        keyboard.append([InlineKeyboardButton("📊 Реклама: отчёт", callback_data="ad_page_1_1")])

    await msg.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )


async def cb_vae_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик выбора VAE из коллбэка"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    callback_data = query.data  # например: "vae_sdxl_vae.safetensors" или "vae_null"

    if callback_data == "vae_null":
        vae_value = None
        msg = "🔄 VAE сброшен: теперь используется автоподбор под модель"
    else:
        # Парсим: "vae_filename.safetensors" → "filename.safetensors"
        vae_value = callback_data.replace("vae_", "", 1)
        msg = f"✅ Установлен VAE: <code>{vae_value}</code>"

    await update_user_settings(user_id, username=None, vae=vae_value)

    await query.edit_message_text(msg, parse_mode="HTML")