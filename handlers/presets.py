from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import telegram
import logging
from telegram.ext import ContextTypes
import config
from models.users_presets import add_user_preset, list_user_presets, get_user_preset
from models.user_state import update_user_settings, get_user_settings
from config import PRESETS
from services.forge_options import ForgeOptionsCache

logger = logging.getLogger(__name__)

# Шаги мастера (теперь 10)
(STEP_NAME, STEP_KEY, STEP_PROMPT, STEP_NEGATIVE, STEP_RESOLUTION,
 STEP_STEPS, STEP_CFG, STEP_SAMPLER, STEP_SCHEDULER, STEP_CONFIRM) = range(10)

# Хранилище сессий
_wizard_state: dict[int, dict] = {}


# =============================================================================
# === ЕДИНЫЙ РОУТЕР КНОПОК ПРЕСЕТОВ ============================================
# =============================================================================

async def preset_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ловит все callback_data, начинающиеся с 'preset' или 'presets'"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # Открыть меню пресетов
    if data in ("presets", "presets_list"):
        await _show_presets_menu(update, context)
        return

    # Активация пресета
    if data.startswith("preset_activate:"):
        key = data.split(":", 1)[1]
        await update_user_settings(user_id, preset=key)
        await _show_presets_menu(update, context)
        return

    # Удаление кастомного пресета
    if data.startswith("preset_delete:"):
        key = data.split(":", 1)[1]
        from models.users_presets import delete_user_preset
        settings = await get_user_settings(user_id)
        if settings.get('preset') == key:
            await update_user_settings(user_id, preset=None)
        await delete_user_preset(user_id, key)
        await _show_presets_menu(update, context)
        return

    # 3️⃣ Старт создания
    if data == "preset_create_start":
        _wizard_state[user_id] = {"step": STEP_NAME, "data": {}}
        await query.edit_message_text(
            "🎨 <b>Создание пресета</b>\n\n"
            "Шаг 1/10: Введите <b>название</b> (до 30 символов):\n"
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
        await query.message.reply_text("Шаг 6/10: Выберите <b>шаги генерации</b>:",
                                       reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        return

    # 5️⃣ Выбор шагов → переход к CFG (текст)
    if data.startswith("preset_steps:"):
        _wizard_state[user_id]["data"]["steps"] = int(data.split(":")[1])
        _wizard_state[user_id]["step"] = STEP_CFG
        await query.message.reply_text(
            "Шаг 7/10: <b>CFG Scale</b> (влияет на соответствие промпту):\n"
            "Обычно <code>5.0</code>–<code>8.0</code>. Оставьте <code>7.0</code>, если не уверены.\n"
            "Отправьте число:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="preset_step_back")]]),
            parse_mode="HTML"
        )
        return

    # 🔽 ШАГ 8: Выбор сэмплера (кнопки)
    if data.startswith("preset_sampler:"):
        _wizard_state[user_id]["data"]["sampler_name"] = data.split(":", 1)[1]
        _wizard_state[user_id]["step"] = STEP_SCHEDULER

        kb = []
        schedulers = list(config.SCHEDULERS.items())
        for i in range(0, len(schedulers), 3):
            kb.append([InlineKeyboardButton(n, callback_data=f"preset_sched:{v}") for n, v in schedulers[i:i + 3]])
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="preset_step_back")])

        await query.message.reply_text(
            "Шаг 9/10: <b>Выбери расписание (Scheduler)</b>:\n"
            "🔹 <code>Karras</code> — для DPM++ (детальнее)\n"
            "🔹 <code>Automatic</code> — стандарт",
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
        )
        return

    # 🔽 ШАГ 9: Выбор расписания → подтверждение
    if data.startswith("preset_sched:"):
        _wizard_state[user_id]["data"]["scheduler"] = data.split(":", 1)[1]
        _wizard_state[user_id]["step"] = STEP_CONFIRM
        await _show_confirmation(query.message, user_id)
        return

    # 🔙 Назад в мастере (динамический)
    if data == "preset_step_back":
        current = _wizard_state[user_id]["step"]

        if current == STEP_CFG:
            _wizard_state[user_id]["step"] = STEP_RESOLUTION
            await query.edit_message_text("Шаг 5/10: Выберите <b>разрешение</b>:", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("512x768 📸", callback_data="preset_res:512x768"),
                 InlineKeyboardButton("768x512 🌆", callback_data="preset_res:768x512")],
                [InlineKeyboardButton("512x512", callback_data="preset_res:512x512"),
                 InlineKeyboardButton("768x768", callback_data="preset_res:768x768")],
                [InlineKeyboardButton('1024x1024', callback_data="preset_res:1024x1024"),
                 InlineKeyboardButton('832x1216', callback_data="preset_res:832x1216")],
                [InlineKeyboardButton('1216x832', callback_data="preset_res:1216x832"),
                 InlineKeyboardButton('1344x768', callback_data="preset_res:1344x768")],
            ]), parse_mode="HTML")

        elif current == STEP_SAMPLER:
            _wizard_state[user_id]["step"] = STEP_CFG
            await query.edit_message_text(
                "Шаг 7/10: <b>CFG Scale</b> (5.0–8.0):\nОтправьте число:",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Назад", callback_data="preset_step_back")]]),
                parse_mode="HTML"
            )

        elif current == STEP_SCHEDULER:
            _wizard_state[user_id]["step"] = STEP_SAMPLER
            kb = []
            samplers = list(config.SAMPLERS.items())
            for i in range(0, len(samplers), 2):
                kb.append([InlineKeyboardButton(n, callback_data=f"preset_sampler:{v}") for n, v in samplers[i:i + 2]])
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="preset_step_back")])

            await query.edit_message_text("Шаг 8/10: Выбери сэмплер:", reply_markup=InlineKeyboardMarkup(kb),
                                          parse_mode="HTML")
        else:
            _wizard_state[user_id]["step"] = max(STEP_NAME, current - 1)
            await query.edit_message_text(f"🔙 Шаг возвращен. Повторите ввод.", parse_mode="HTML")
        return

    # 💾 Сохранить / Отмена
    if data == "preset_save":
        await _save_and_activate(query, user_id)
    elif data == "preset_cancel":
        _wizard_state.pop(user_id, None)
        await query.edit_message_text("🗑️ Создание отменено.", parse_mode="HTML")


# =============================================================================
# === МЕНЮ ПРЕСЕТОВ ==========================================================
# =============================================================================

async def _show_presets_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    settings = await get_user_settings(user_id)
    current = settings.get('preset')
    custom_presets = await list_user_presets(user_id)

    kb = []
    for key, cfg in PRESETS.items():
        active = "✅ " if key == current else ""
        kb.append([InlineKeyboardButton(f"{active}{cfg['name']}", callback_data=f"preset_activate:{key}")])

    if custom_presets:
        for p in custom_presets:
            active = "✅ " if p['preset_key'] == current else ""
            kb.append([
                InlineKeyboardButton(f"{active}{p['name']} ({p['width']}x{p['height']})",
                                     callback_data=f"preset_activate:{p['preset_key']}"),
                InlineKeyboardButton("🗑️", callback_data=f"preset_delete:{p['preset_key']}")
            ])

    kb.append([InlineKeyboardButton("➕ Создать свой", callback_data="preset_create_start")])
    kb.append([InlineKeyboardButton("❌ Назад", callback_data="main_menu")])

    try:
        await query.edit_message_text(
            "🎨 <b>Выберите стиль генерации</b>:\nАктивный стиль автоматически применяется к /gen",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="HTML"
        )
    except telegram.error.BadRequest as e:
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
            "Шаг 2/10: Введите <b>ключ</b> (латиница, цифры, _):\nПример: <code>my_style</code>", parse_mode="HTML")

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
            "Шаг 3/10: <b>Промпт-суффикс</b> (опционально):\n↩️ <code>skip</code> — пропустить", parse_mode="HTML")

    elif step == STEP_PROMPT:
        state["data"]["prompt_suffix"] = "" if text.lower() == "skip" else f", {text}"
        state["step"] = STEP_NEGATIVE
        await update.message.reply_text(
            "Шаг 4/10: <b>Негативный промпт</b> (опционально):\n↩️ <code>skip</code> — пропустить", parse_mode="HTML")

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
        ]
        await update.message.reply_text("Шаг 5/10: Выберите <b>разрешение</b>:", reply_markup=InlineKeyboardMarkup(kb),
                                        parse_mode="HTML")

    elif step == STEP_CFG:
        try:
            cfg = float(text.replace(',', '.'))
            if not (1.0 <= cfg <= 30.0): raise ValueError
            state["data"]["cfg_scale"] = cfg
            state["step"] = STEP_SAMPLER

            # Показываем кнопки сэмплеров
            kb = []
            samplers = list(config.SAMPLERS.items())
            for i in range(0, len(samplers), 2):
                kb.append([InlineKeyboardButton(n, callback_data=f"preset_sampler:{v}") for n, v in samplers[i:i + 2]])
            kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="preset_step_back")])

            await update.message.reply_text(
                "Шаг 8/10: <b>Выбери сэмплер</b> (алгоритм генерации):",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML"
            )
        except ValueError:
            await update.message.reply_text("❌ Введите число от 1.0 до 30.0 (например, 7.0)")
            return


async def _show_confirmation(message, user_id: int):
    d = _wizard_state[user_id]["data"]
    cfg = d.get("cfg_scale", 7.0)
    sampler = d.get("sampler_name", "Euler")
    scheduler = d.get("scheduler", "Automatic")

    await message.reply_text(
        f"✅ <b>Готово к сохранению</b>\n"
        f"🏷️ {d['name']}\n🔑 <code>{d['preset_key']}</code>\n"
        f"📐 {d['width']}x{d['height']} | 🔢 {d['steps']} шагов | ⚖️ CFG: {cfg}\n"
        f"🔄 Сэмплер: <code>{sampler}</code> | 📅 Scheduler: <code>{scheduler}</code>\n\nСохранить?",
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
        cfg_scale=d.get("cfg_scale", 7.0),
        sampler=d.get("sampler_name", "Euler"),
        scheduler=d.get("scheduler", "Automatic")
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


async def quick_preset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    🚀 Быстрое создание пресета в одну строку.
    Работает с пробелами без кавычек: /preset_add name=Аниме Киберпанк key=anime prompt=neon city
    """
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(
            "❌ Использование:\n"
            "`/preset_add name=<str> key=<str> [res=512x768] [steps=25] [cfg=7.0] [sampler=...] [scheduler=...] [prompt=...] [negative=...]`\n"
            "💡 Пробелы в значениях работают автоматически. Кавычки необязательны.",
            parse_mode="Markdown"
        )
        return

    # 🔍 Умный парсер флагов (поддерживает пробелы в значениях)
    args = {}
    current_key = None
    try:
        for arg in context.args:
            if '=' in arg:
                key, val = arg.split('=', 1)
                args[key.lower().strip()] = val.strip()
                current_key = key.lower().strip()
            elif current_key is not None:
                # Это продолжение предыдущего значения (пробел внутри аргумента)
                args[current_key] += ' ' + arg
            else:
                return await update.message.reply_text(f"❌ Неверный формат: `{arg}`. Ожидается `ключ=значение`")

        # Очистка от кавычек (если пользователь всё же их поставил)
        for k in args:
            args[k] = args[k].strip().strip("\"'").strip()
    except Exception:
        return await update.message.reply_text("❌ Ошибка парсинга. Проверьте формат `ключ=значение`")

    # 📋 Обязательные поля
    name = args.get("name")
    key = args.get("key")
    if not name or len(name) > 30:
        return await update.message.reply_text("❌ `name` обязателен (1-30 символов)")
    if not key or not all(c.isalnum() or c == '_' for c in key.lower()):
        return await update.message.reply_text("❌ `key` обязателен (латиница, цифры, _)")

    if await get_user_preset(user_id, key.lower()):
        return await update.message.reply_text(f"❌ Ключ `{key}` уже занят")

    # 📐 Разрешение
    res_str = args.get("res", "512x768")
    try:
        max_res = 1344  # Чтобы видеокарта не плакала
        w, h = map(int, res_str.split("x"))
        if not (128 <= w <= max_res and 128 <= h <= max_res): raise ValueError
    except:
        return await update.message.reply_text("❌ `res` в формате `WxH` (например: 512x768)")

    # 🔢 Шаги
    try:
        steps = int(args.get("steps", "25"))
        if not (10 <= steps <= 150): raise ValueError
    except:
        return await update.message.reply_text("❌ `steps` должно быть числом от 10 до 150")

    # ⚖️ CFG
    try:
        cfg = float(args.get("cfg", "7.0").replace(",", "."))
        if not (1.0 <= cfg <= 30.0): raise ValueError
    except:
        return await update.message.reply_text("❌ `cfg` должно быть числом от 1.0 до 30.0")

    await ForgeOptionsCache.ensure_loaded()

    # Сэмплер & Шедулер (регистронезависимо)
    sampler_in = args.get("sampler", "Euler")
    sched_in = args.get("scheduler", "automatic")

    if not ForgeOptionsCache.is_valid_sampler(sampler_in):
        available = ", ".join(ForgeOptionsCache.get_samplers()[:10])  # Показываем первые 10
        return await update.message.reply_text(f"❌ Неизвестный `sampler`. Примеры: {available}")

    if not ForgeOptionsCache.is_valid_scheduler(sched_in):
        available = ", ".join(ForgeOptionsCache.get_schedulers()[:10])
        return await update.message.reply_text(f"❌ Неизвестный `scheduler`. Примеры: {available}")

    sampler_final = next((s for s in ForgeOptionsCache.get_samplers() if s.lower() == sampler_in.lower()), sampler_in)
    sched_final = next((s for s in ForgeOptionsCache.get_schedulers() if s.lower() == sched_in.lower()), sched_in)

    # 📝 Промпты
    prompt = f", {args['prompt']}" if "prompt" in args else ""
    negative = args.get("negative", "")

    # 💾 Сохранение
    success = await add_user_preset(
        user_id=user_id, preset_key=key.lower(), name=name,
        prompt_suffix=prompt, negative_suffix=negative,
        width=w, height=h, steps=steps,
        cfg_scale=cfg, sampler=sampler_final, scheduler=sched_final
    )

    if success:
        await update.message.reply_text(
            f"✅ Пресет создан!\n"
            f"🔑 `{key.lower()}` | 🏷️ `{name}`\n"
            f"📐 {w}x{h} | 🔢 {steps} | ⚖️ {cfg}\n"
            f"🔄 {sampler_final} | 📅 {sched_final}\n"
            f"📝 Промпт: `{prompt or '(пусто)'}`\n\n"
            f"Активируйте: `/preset` → `🔑 {key.lower()}`",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Ошибка при сохранении (проверьте логи)")

async def list_samplers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает доступные сэмплеры из Forge"""
    await ForgeOptionsCache.ensure_loaded()
    samplers = ForgeOptionsCache.get_samplers()
    text = "🔄 **Доступные сэмплеры**:\n" + "\n".join(f"• `{s}`" for s in sorted(samplers)[:20])
    if len(samplers) > 20:
        text += f"\n_...и ещё {len(samplers) - 20}_"
    await update.message.reply_text(text, parse_mode="Markdown")

async def list_schedulers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает доступные шедулеры из Forge"""
    await ForgeOptionsCache.ensure_loaded()
    schedulers = ForgeOptionsCache.get_schedulers()
    text = "📅 **Доступные шедулеры**:\n" + "\n".join(f"• `{s}`" for s in sorted(schedulers))
    await update.message.reply_text(text, parse_mode="Markdown")

async def refresh_forge_options_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ-команда: принудительно обновляет кеш из Forge"""
    if update.effective_user.id not in config.ADMINS:
        return
    await update.message.reply_text("🔄 Обновляю список опций из Forge...")
    await ForgeOptionsCache.refresh()
    await update.message.reply_text(
        f"✅ Готово!\n"
        f"🔄 Сэмплеров: {len(ForgeOptionsCache.get_samplers())}\n"
        f"📅 Шедулеров: {len(ForgeOptionsCache.get_schedulers())}"
    )