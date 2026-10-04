"""
Команды бота: генерация, пресеты, настройки, история.
Архитектура: тонкий слой оркестрации → вся логика в services/utils.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from models.promo_codes import reward_referral_creator
import asyncio

logger = logging.getLogger(__name__)


# =============================================================================
# === КОМАНДЫ ==================================================================
# =============================================================================
# В начало файла (импорты) — если ещё нет:
# from models.user_quota import _get_or_create_quota, add_paid_credits


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    # Если нужно сбрасывать/инициализировать настройки при старте:
    # await update_user_settings(user.id, user.first_name, model=None, preset=None)

    # 1. Кнопка Web App (Reply Keyboard - самая надежная для sendData)
    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(text="🎨 Открыть Конструктор артов", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

    # 2. Инлайн кнопки для остального меню
    inline_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("📚 Пресеты", callback_data="presets")],
        [InlineKeyboardButton("📖 Гайд для новичка", url="https://telegra.ph/Minigajd-po-risovaniyu-05-16")]
    ])

    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🎨 Я — твой помощник для генерации красивых артов.\n\n"
        "💡 *Нажми большую кнопку ниже*, чтобы собрать промпт без знания тегов. "
        "Я сам добавлю качество и отправлю его в очередь!\n\n"
        "Или пиши вручную: `/gen cute anime girl`\n\n"
        "🐾 *Хочешь бесплатные генерации?*\n"
        "Используй `/my_referral`, чтобы получить свой бонусный код. "
        "Поделись им с другом: он получит халявные арты, а ты — награду!"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_keyboard,
        parse_mode="Markdown"
    )

    # Следом отправляем инлайн меню (опционально, или объедини их, если хочешь)
    await update.message.reply_text(
        "👇 Доп. меню:",
        reply_markup=inline_keyboard,
        parse_mode="Markdown"
    )


async def generate(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        queue_manager,
        custom_prompt: str = None,
        overrides: dict = None
) -> None:
    user = update.effective_user
    if not user:
        return
    user_id = user.id

    # 1. Проверка лимитов
    usage_type = await check_user_limits(update, user_id)
    if usage_type is None:
        return

    # 2. Извлечение промпта
    if custom_prompt:
        prompt = custom_prompt
    else:
        prompt = extract_prompt(update, context)

    if prompt is None:
        await update.effective_message.reply_text("⚠️ Укажи промпт.")
        return

    # 3. Перевод / валидация
    prompt = await prepare_prompt(update, prompt)
    if prompt is None:
        return

    # 4. Сборка базового payload
    settings = await get_user_settings(user_id)
    safe_preset = settings.get("preset") or "nova_anime_vertical"
    safe_model = settings.get("model") or config.DEFAULT_MODEL

    payload, _, _ = await build_generation_payload(
        user_id=user_id,
        prompt=prompt,
        preset_key=safe_preset,
        model_name=safe_model,
        lora_string=settings.get("lora_string")
    )

    # 🔥 ПРИМЕНЕНИЕ ПЕРЕОПРЕДЕЛЕНИЙ (OVERRIDES)
    if overrides:
        for key, value in overrides.items():
            payload[key] = value
            logger.info(f"🔧 Применен override: {key} = {value}")

    # 5. Отправка в очередь
    progress_msg = await update.effective_message.reply_text("⏳ Подключение к очереди...")

    try:
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

        #  ТРИГГЕР РЕФЕРАЛЬНОГО БОНУСА (Теперь надежно ждем выполнения)
        # Функция сама проверит, есть ли реферал, и начислит бонус создателю
        await reward_referral_creator(user_id)

    except Exception as e:
        logger.error(f"❌ Ошибка очереди: {e}", exc_info=True)
        await update.effective_message.reply_text("❌ Ошибка при постановке в очередь.")


from presets import PRESETS  # Добавь этот импорт в начало файла, если его нет


async def preset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню выбора пресетов (стандартные + кастомные + управление)"""
    keyboard = []

    # Стандартные пресеты
    for key, cfg in PRESETS.items():
        keyboard.append([InlineKeyboardButton(cfg["name"], callback_data=f"preset_activate:{key}")])

    # Разделитель
    keyboard.append([InlineKeyboardButton("➖➖➖➖➖➖➖➖➖➖", callback_data="ignore")])

    # Кастомные пресеты и управление
    keyboard.append([
        InlineKeyboardButton("📋 Мои пресеты", callback_data="presets_list"),
        InlineKeyboardButton("➕ Создать", callback_data="preset_create_start")
    ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])

    await update.message.reply_text(
        "🎨 <b>Выберите стиль генерации</b>:\n"
        "Активный стиль автоматически применяется к <code>/gen</code>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


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

    def cfg(key, fallback=""):
        return p.get(key, config.DEFAULTS.get(key, fallback)) if p else config.DEFAULTS.get(key, fallback)

    s = await get_user_settings(user.id)
    preset_key = s.get("preset")
    p = await get_user_preset(user.id, preset_key) if (preset_key and preset_key not in PRESETS) else None
    if not p:
        p = PRESETS.get(preset_key)
        sampler =  cfg("sampler_name")
    else:
        sampler = cfg("sampler")

    info = {
        "🧠 Модель": s.get("model") or "default",
        "🎨 Пресет": preset_key or "нет",
        "🔧 VAE": s.get("vae") or "Автоподбор",
        "🧩 LoRA": s.get("lora_string") or "не заданы",
        "📏 Размер": f"{cfg('width')}×{cfg('height')}",
        "🔢 Шаги": cfg("steps"),
        "⚖️ CFG": cfg("cfg_scale"),
        "🔄 Сэмплер": sampler,
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
        pr = h['prompt'][:40] + "..." if h.get('prompt') and len(h['prompt']) > 40 else (h.get('prompt') or '—')
        # 🔥 ФИКС: защита от None в generation_time_sec
        time_sec = h.get('generation_time_sec')
        time_str = f"{time_sec:.1f}с" if time_sec is not None else "—"
        lines.append(f"{i}. {st} `{pr}` | ⏱ {time_str}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def loras_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return

    if update.callback_query:
        await update.callback_query.answer()

    loras = fetch_available_loras(user_id=update.effective_user.id if update.effective_user else None)
    if not loras:
        await msg.reply_text("📭 LoRA не найдены или API недоступен.")
        return

    lines = ["🧩 Доступные LoRA:\n"]
    for l in loras[:20]:
        alias = l.get('alias', l['name'])
        name = l['name']
        lines.append(f"• `{alias}` → `<lora:{name}:1.0>`")

    lines.append("\n💡 Скопируй тег и вставь прямо в промпт.")
    lines.append("💾 Или сохрани набор: `/lora_set <lora:name:0.8> <lora:name2:0.5>`")

    # 👇 ДОБАВЛЯЕМ ССЫЛКУ НА ШПАРГАЛКУ
    lines.append("\n📖 [Полная шпаргалка с триггерами LoRA](https://t.me/loras_for_MyNekoBaka)")

    await msg.reply_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)


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


async def open_app_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Возвращает кнопку Web App, если она пропала"""

    # Создаем ТУ САМУЮ клавиатуру, которая гарантированно работает
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(text="🎨 Открыть Конструктор артов", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True,
        one_time_keyboard=False  # ← ЭТО ГЛАВНОЕ: клавиатура НЕ исчезнет после нажатия
    )

    await update.effective_message.reply_text(
        "🎨 Конструктор артов готов к работе!\n"
        "Нажми на кнопку ниже, чтобы создать запрос.",
        reply_markup=keyboard
    )