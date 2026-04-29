"""
Команды бота: генерация, пресеты, настройки, история.
Архитектура: тонкий слой оркестрации → вся логика в services/utils.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from models.generation_log import get_user_history
from models.user_state import get_user_settings, update_user_settings
from models.users_presets import get_user_preset
from services.forge_api import fetch_available_models, fetch_available_vae,fetch_available_loras
from services.payload_builder import build_generation_payload
from services.generation_pipeline import check_user_limits, submit_to_queue
from utils.prompt_utils import extract_prompt, prepare_prompt
import html

logger = logging.getLogger(__name__)


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
    if not user:
        return
    user_id = user.id

    # 1. Проверка лимитов
    usage_type = await check_user_limits(update, user_id)
    if usage_type is None:
        return

    # 2. Извлечение промпта
    prompt = extract_prompt(update, context)
    if prompt is None:
        await update.message.reply_text("❌ Укажи промпт. Пример: `/gen cyberpunk city`")
        return

    # 3. Перевод / валидация промпта
    prompt = await prepare_prompt(update, prompt)
    if prompt is None:
        return

    # 4. Сборка payload
    settings = await get_user_settings(user_id)
    payload, _, _ = await build_generation_payload(
        user_id=user_id,
        prompt=prompt,
        preset_key=settings.get("preset"),
        model_name=settings.get("model") or config.DEFAULT_MODEL,
        lora_string=settings.get("lora_string")
    )

    # 5. Отправка в очередь
    progress_msg = await update.message.reply_text("⏳ Подключение к очереди...")
    await submit_to_queue(
        user_id=user_id,
        prompt=prompt,
        payload=payload,
        settings=settings,
        update=update,
        progress_msg=progress_msg,
        queue_manager=queue_manager,
        usage_type=usage_type
    )


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
    preset_key = s.get("preset")
    p = await get_user_preset(user.id, preset_key) if (preset_key and preset_key not in config.PRESETS) else None

    def cfg(key, fallback=""):
        return p.get(key, config.DEFAULTS.get(key, fallback)) if p else config.DEFAULTS.get(key, fallback)

    info = {
        "🧠 Модель": s.get("model") or "default",
        "🎨 Пресет": preset_key or "нет",
        "🔧 VAE": s.get("vae") or "Автоподбор",
        "🧩 LoRA": s.get("lora_string") or "не заданы",
        "📏 Размер": f"{cfg('width')}×{cfg('height')}",
        "🔢 Шаги": cfg("steps"),
        "⚖️ CFG": cfg("cfg_scale"),
        "🔄 Сэмплер": cfg("sampler_name"),
        "📅 Шедулер": cfg("scheduler") or config.DEFAULTS.get("scheduler", "karras"),
    }

    # ✅ Экранируем все динамические значения для безопасного HTML
    txt = "⚙️ <b>Настройки генерации:</b>\n" + "\n".join(
        f"{k}: <code>{html.escape(str(v))}</code>" for k, v in info.items()
    )

    await update.message.reply_text(
        txt,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Главное меню", callback_data="main_menu")
        ]])
    )


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


async def loras_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ✅ Универсальный способ получить объект сообщения (работает и для /command, и для кнопки)
    msg = update.effective_message
    if not msg:
        return

    # ✅ Если это клик по кнопке, обязательно отвечаем серверу Telegram, чтобы не крутилось "часики"
    if update.callback_query:
        await update.callback_query.answer()


    loras = fetch_available_loras(user_id = update.effective_user.id if update.effective_user else None)
    if not loras:
        await msg.reply_text("📭 LoRA не найдены или API недоступен.")
        return

    lines = ["🧩 Доступные LoRA:\n"]
    for l in loras[:20]:
        alias = l.get('alias', l['name'])
        name = l['name']
        lines.append(f"• `{alias}` → `<lora:{name}:1.0>`")

    lines.append("\n💡 Скопируй тег и вставь прямо в промпт.")
    lines.append("💾 Или сохри набор: `/lora_set <lora:name:0.8> <lora:name2:0.5>`")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown")


async def lora_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сохраняет строку LoRA в профиль пользователя."""
    if not context.args:
        await update.message.reply_text(
            "❌ Формат: `/lora_set <тег> [<тег> ...]`\n"
            "Пример: `/lora_set <lora:epiCRealism:0.7>`"
        )
        return

    lora_str = " ".join(context.args).strip()
    await update_user_settings(update.effective_user.id, lora_string=lora_str if lora_str else None)
    await update.message.reply_text(
        f"✅ {'LoRA очищены' if not lora_str else 'LoRA сохранены'}: `{lora_str or '—'}`"
    )

async def lora_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очищает сохранённые LoRA-теги у пользователя."""
    await update_user_settings(update.effective_user.id, lora_string=None)
    await update.message.reply_text("🧹 LoRA-теги сброшены. Генерация пойдёт без них.")