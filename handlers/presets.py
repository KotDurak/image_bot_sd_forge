# handlers/presets.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import telegram
import logging

from models.users_presets import add_user_preset, list_user_presets, get_user_preset
from models.user_state  import update_user_settings, get_user_settings
from config import PRESETS

logger = logging.getLogger(__name__)

# Состояние мастера
_wizard_state: dict[int, dict] = {}
STEP_NAME, STEP_KEY, STEP_PROMPT, STEP_NEGATIVE, STEP_RESOLUTION, STEP_STEPS, STEP_CONFIRM = range(7)


# =============================================================================
# === ЕДИНЫЙ РОУТЕР КНОПОК ПРЕСЕТОВ ============================================
# =============================================================================

async def preset_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловит все callback_data, начинающиеся с 'preset' или 'presets'"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    #Открыть меню пресетов
    if data in ("presets", "presets_list"):
        await _show_presets_menu(update, context)
        return

    # Активация пресета (системного или кастомного)
    if data.startswith("preset_activate:"):
        key = data.split(":", 1)[1]
        await update_user_settings(user_id, preset=key)
        await _show_presets_menu(update, context)  # Обновит список, ошибка "not modified" поймается внутри
        return

    # Удаление кастомного пресета
    if data.startswith("preset_delete:"):
        key = data.split(":", 1)[1]
        from models.users_presets import delete_user_preset

        # Если удаляем активный пресет — сбрасываем настройку
        settings = await get_user_settings(user_id)
        current = settings.get('preset')
        if current == key:
            await update_user_settings(user_id, preset=None)

        await delete_user_preset(user_id, key)  # Логирует внутри
        await _show_presets_menu(update, context)  # Обновляем список
        return


    # 3️⃣ Старт создания
    if data == "preset_create_start":
        _wizard_state[user_id] = {"step": STEP_NAME, "data": {}}
        await query.edit_message_text(
            "🎨 <b>Создание пресета</b>\n\n"
            "Шаг 1/7: Введите <b>название</b> (до 30 символов):\n"
            "↩️ <code>/cancel</code> — отменить",
            parse_mode="HTML"
        )
        return

    # 4️⃣ Выбор разрешения
    if data.startswith("preset_res:"):
        w, h = map(int, data.split(":")[1].split("x"))
        _wizard_state[user_id]["data"].update({"width": w, "height": h})
        _wizard_state[user_id]["step"] = STEP_STEPS

        kb = [
            [InlineKeyboardButton("20 ⚡", callback_data="preset_steps:20"),
             InlineKeyboardButton("25 🎯", callback_data="preset_steps:25")],
            [InlineKeyboardButton("30 ✨", callback_data="preset_steps:30"),
             InlineKeyboardButton("40 🔥", callback_data="preset_steps:40")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="preset_step_back")]
        ]
        await query.message.reply_text("Шаг 6/7: Выберите <b>шаги генерации</b>:",
                                       reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        return

    # 5️⃣ Выбор шагов
    if data.startswith("preset_steps:"):
        _wizard_state[user_id]["data"]["steps"] = int(data.split(":")[1])
        _wizard_state[user_id]["step"] = STEP_CONFIRM
        await _show_confirmation(query.message, user_id)
        return

    # 6️⃣ Назад в мастере
    if data == "preset_step_back":
        _wizard_state[user_id]["step"] = STEP_NEGATIVE
        await query.edit_message_text("Шаг 4/7: Введите <b>негативный промпт</b>:\n↩️ <code>skip</code> — пропустить",
                                      parse_mode="HTML")
        return

    # 7️⃣ Сохранить / Отмена
    if data == "preset_save":
        await _save_and_activate(query, user_id)
    elif data == "preset_cancel":
        _wizard_state.pop(user_id, None)
        await query.edit_message_text("🗑️ Создание отменено.", parse_mode="HTML")


# =============================================================================
# === МЕНЮ ПРЕСЕТОВ (СИСТЕМНЫЕ + КАСТОМНЫЕ) ====================================
# =============================================================================

async def _show_presets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список пресетов + кнопку создания"""
    query = update.callback_query
    user_id = update.effective_user.id
    settings = await get_user_settings(user_id)
    current = settings.get('preset')
    custom_presets = await list_user_presets(user_id)

    kb = []
    # 1. Системные пресеты (из config.PRESETS)
    for key, cfg in PRESETS.items():
        active = "✅ " if key == current else ""
        kb.append([InlineKeyboardButton(f"{active}{cfg['name']}", callback_data=f"preset_activate:{key}")])

    # 2. Кастомные пресеты (из БД)
    if custom_presets:
        kb.append([InlineKeyboardButton("— Ваши пресеты —", callback_data="sep_custom")])
        for p in custom_presets:
            active = "✅ " if p['preset_key'] == current else ""
            kb.append(
                [InlineKeyboardButton(f"{active}{p['name']} ({p['width']}x{p['height']})",
                                            callback_data=f"preset_activate:{p['preset_key']}"),
                       InlineKeyboardButton("🗑️", callback_data=f"preset_delete:{p['preset_key']}")
           ])

    # 3. Действия
    kb.append([InlineKeyboardButton("➕ Создать свой", callback_data="preset_create_start")])
    kb.append([InlineKeyboardButton("❌ Назад", callback_data="main_menu")])

    try:
        await query.edit_message_text(
            "🎨 <b>Выберите стиль генерации</b>:\nАктивный стиль автоматически применяется к /gen",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML"
        )
    except telegram.error.BadRequest as e:
        # Игнорируем ошибку, если контент не изменился
        if "Message is not modified" not in str(e):
            raise


# =============================================================================
# === ТЕКСТОВЫЙ ВВОД В МАСТЕРЕ =================================================
# =============================================================================

async def handle_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in _wizard_state:
        return

    text = update.message.text.strip()
    state = _wizard_state[user_id]
    step = state["step"]

    if step == STEP_NAME:
        if not text or len(text) > 30:
            await update.message.reply_text("❌ Название: 1-30 символов.")
            return
        state["data"]["name"] = text
        state["step"] = STEP_KEY
        await update.message.reply_text(
            "Шаг 2/7: Введите <b>ключ</b> (латиница, цифры, _):\nПример: <code>my_style</code>", parse_mode="HTML")

    elif step == STEP_KEY:
        key = text.lower().strip()
        if not key or not all(c.isalnum() or c == '_' for c in key):
            await update.message.reply_text("❌ Только латиница, цифры, _.")
            return
        if await get_user_preset(user_id, key):
            await update.message.reply_text("❌ Ключ уже занят.")
            return
        state["data"]["preset_key"] = key
        state["step"] = STEP_PROMPT
        await update.message.reply_text(
            "Шаг 3/7: <b>Промпт-суффикс</b> (опционально):\n↩️ <code>skip</code> — пропустить", parse_mode="HTML")

    elif step == STEP_PROMPT:
        state["data"]["prompt_suffix"] = "" if text.lower() == "skip" else f", {text}"
        state["step"] = STEP_NEGATIVE
        await update.message.reply_text(
            "Шаг 4/7: <b>Негативный промпт</b> (опционально):\n↩️ <code>skip</code> — пропустить", parse_mode="HTML")

    elif step == STEP_NEGATIVE:
        state["data"]["negative_suffix"] = "" if text.lower() == "skip" else text
        state["step"] = STEP_RESOLUTION

        kb = [
            [InlineKeyboardButton("512x768 📸", callback_data="preset_res:512x768"),
             InlineKeyboardButton("768x512 🌆", callback_data="preset_res:768x512")],
            [InlineKeyboardButton("512x512", callback_data="preset_res:512x512"),
             InlineKeyboardButton("768x768", callback_data="preset_res:768x768")],
            [InlineKeyboardButton('1024x1024', callback_data="preset_res:1024x1024"),
             InlineKeyboardButton('832x1216', callback_data="preset_res:832x1216")],
            [InlineKeyboardButton('1216x832', callback_data="preset_res:1216x832"),
             InlineKeyboardButton('1344x768', callback_data="preset_res:1344x768")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="preset_step_back")]
        ]
        await update.message.reply_text("Шаг 5/7: Выберите <b>разрешение</b>:", reply_markup=InlineKeyboardMarkup(kb),
                                        parse_mode="HTML")


async def _show_confirmation(message, user_id: int):
    d = _wizard_state[user_id]["data"]
    await message.reply_text(
        f"✅ <b>Готово к сохранению</b>\n🏷️ {d['name']}\n🔑 <code>{d['preset_key']}</code>\n📐 {d['width']}x{d['height']}, {d['steps']} шагов\n\nСохранить?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Сохранить", callback_data="preset_save"),
             InlineKeyboardButton("❌ Отмена", callback_data="preset_cancel")]
        ]), parse_mode="HTML"
    )


async def _save_and_activate(query, user_id: int):
    d = _wizard_state[user_id]["data"]
    success = await add_user_preset(
        user_id=user_id, preset_key=d["preset_key"], name=d["name"],
        prompt_suffix=d.get("prompt_suffix", ""), negative_suffix=d.get("negative_suffix", ""),
        width=d["width"], height=d["height"], steps=d["steps"],
        is_safe_for_business=True
    )
    if success:
        await update_user_settings(user_id, preset=d["preset_key"])
        await query.edit_message_text(f"✨ Пресет <b>{d['name']}</b> сохранён и активирован!", parse_mode="HTML")
    else:
        await query.edit_message_text("❌ Ошибка (ключ уже занят).", parse_mode="HTML")
    _wizard_state.pop(user_id, None)


async def cancel_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in _wizard_state:
        _wizard_state.pop(user_id, None)
        await update.message.reply_text("🗑️ Мастер отменён.", parse_mode="HTML")
    else:
        await update.message.reply_text("✅ Нет активного мастера.", parse_mode="HTML")