import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext
from services.forge_api import fetch_available_models
from models.user_state import get_user_settings, update_user_settings
from presets import get_preset_list
import config

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
                update_user_settings(user_id, query.from_user.username, model=full_name)
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
    update_user_settings(query.from_user.id, query.from_user.username, preset=preset_key)
    await query.edit_message_text(
        f"✅ Применён пресет: **{preset_name}**\n\n"
        "Теперь напиши промпт после /gen — пресет автоматически добавит нужные детали!",
        parse_mode="Markdown"
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущие настройки через inline-кнопки"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    settings = get_user_settings(user_id)  # ✅ Используем новую функцию

    current_model = settings.get("model")
    current_preset = settings.get("preset")

    # Красивые названия для отображения
    model_display = current_model.split('/')[-1] if current_model else "по умолчанию"

    preset_display = "не выбран"
    if current_preset and current_preset in config.PRESETS:
        preset_display = config.PRESETS[current_preset].get("name", current_preset)

    text = (
        "⚙️ **Ваши текущие настройки**:\n\n"
        f"🧠 Модель: `{model_display}`\n"
        f"🎨 Пресет: `{preset_display}`\n"
        f"📏 Размер: {config.DEFAULTS['width']}×{config.DEFAULTS['height']}\n"
        f"🔢 Шаги: {config.DEFAULTS['steps']}\n"
        f"⚖️ CFG: {config.DEFAULTS['cfg_scale']}\n\n"
    )

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🎨 Выбрать модель", callback_data="select_model")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")],
    ]
    await query.edit_message_text("🎛 Главное меню:", reply_markup=InlineKeyboardMarkup(keyboard))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 **Команды бота**:\n\n"
        "/start — начать работу, показать меню\n"
        "/gen <промпт> — сгенерировать изображение\n"
        "/model — открыть выбор моделей\n"
        "/preset — применить стиль-пресет\n"
        "/help — эта справка\n\n"
        "/settings - текущие настройки\n"
        "💡 **Советы для новичка**:\n"
        "• Пиши промпты на английском — результаты лучше",
        parse_mode="Markdown"
    )