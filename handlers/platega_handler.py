import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from pricing import PACKAGES, get_package
from services.platega import create_payment, check_payment_status
from models.user_quota import add_paid_credits
from models.external_payments import save_pending_payment, get_payment_by_id, confirm_payment
from db.async_core import async_db
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

# 🔧 ТЕСТОВЫЙ РЕЖИМ: True = без реальных оплат, для безопасной отладки
TEST_MODE = False


async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        raise


# 1️⃣ Меню выбора пакетов
async def platega_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"📥 Меню: нажата кнопка '{query.data}'")

    kb = []
    for key, pkg in PACKAGES.items():
        # 🔥 ПРЕФИКС pkg_ для выбора пакета
        kb.append([InlineKeyboardButton(
            f"{pkg['label']} — {pkg['price_rub']} ₽",
            callback_data=f"pkg_{key}"
        )])
    kb.append([InlineKeyboardButton("↩️ Назад", callback_data="main_menu")])

    await query.edit_message_text(
        "💳 Выберите пакет для оплаты картой/СБП (Platega):",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# 2️⃣ Создание платежа + сохранение в БД
async def start_platega_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # 🔥 Парсим pkg_{key}
    if not query.data.startswith("pkg_"):
        logger.warning(f"⚠️ start_platega_payment получил неожиданный data: {query.data}")
        return

    package_key = query.data.replace("pkg_", "")
    logger.info(f"🔍 Обработка пакета: '{package_key}'")

    pkg = get_package(package_key)
    if not pkg:
        logger.error(f"❌ Пакет '{package_key}' не найден! Доступные: {list(PACKAGES.keys())}")
        await query.edit_message_text("❌ Пакет не найден. Барсик в шоке 😼")
        return

    user_id = query.from_user.id
    amount_rub = pkg["price_rub"]
    desc = f"Пополнение: {pkg['label']} ({pkg['credits']} генераций)"

    try:
        # 🔥 ТЕСТОВЫЙ РЕЖИМ: фейковый transaction_id
        if TEST_MODE:
            import time
            transaction_id = f"test_{user_id}_{int(time.time())}"
            payment_url = "https://example.com/test"
            logger.info(f"🧪 TEST MODE: фейковый платёж {transaction_id}")
        else:
            res = await create_payment(user_id, package_key, amount_rub, desc)
            transaction_id = res.get("transaction_id")
            payment_url = res.get("payment_url")
            if not transaction_id or not payment_url:
                raise ValueError(f"Platega не вернул нужные поля: {res}")

        # 🔒 Сохраняем в БД и получаем короткий DB id
        payment_id = await save_pending_payment(
            transaction_id=transaction_id,
            user_id=user_id,
            package_key=package_key,
            amount=amount_rub
        )

        # 🔥 ПРЕФИКС pay_ для кнопки проверки (чтобы не путать с pkg_)
        check_data = f"pay_{payment_id}"

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("💳 Перейти к оплате", url=payment_url)
        ], [
            InlineKeyboardButton("✅ Я оплатил", callback_data=check_data)
        ], [
            InlineKeyboardButton("↩️ Назад", callback_data="main_menu")
        ]])

        await safe_edit(
            query,
            f"🛒 **{pkg['label']}**\n💰 Сумма: `{amount_rub}` ₽\n\n"
            f"1️⃣ Перейди по ссылке и оплати.\n"
            f"2️⃣ Вернись в бот и нажми `✅ Я оплатил`.\n"
            f"⏳ Обработка занимает до 1-2 минут.",
            reply_markup=kb,
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Platega create error: {e}")
        await query.edit_message_text("⚠️ Ошибка создания платежа. Попробуйте позже или напишите админу.")


# 3️⃣ Проверка статуса (по DB id → pay_{id})
async def check_platega_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Проверяю статус... ⏳")

    logger.info(f"📥 Проверка статуса: callback_data='{query.data}'")

    # 🔥 Парсим pay_{id}
    if not query.data.startswith("pay_"):
        logger.warning(f"⚠️ check_platega_status получил неожиданный data: {query.data}")
        await safe_edit(query, "❌ Ошибка формата. Напишите админу.")
        return

    try:
        payment_id = int(query.data.replace("pay_", ""))
    except ValueError:
        logger.error(f"❌ Не удалось распарсить payment_id из: {query.data}")
        await safe_edit(query, "❌ Некорректный ID платежа.")
        return

    logger.info(f"🔍 Запрос в БД по payment_id={payment_id}")

    # 🔍 Достаём данные из БД
    payment = await get_payment_by_id(payment_id)
    if not payment:
        logger.error(f"❌ Запись {payment_id} не найдена в external_payments")
        await safe_edit(query, "❌ Платёж не найден в базе. Напишите админу.")
        return

    # 🔥 ТЕСТОВЫЙ РЕЖИМ: считаем, что оплата прошла
    if TEST_MODE:
        status = "confirmed"
        logger.info("🧪 TEST MODE: имитируем подтверждение")
    else:
        status = await check_payment_status(payment['transaction_id'])
        logger.info(f"📡 Статус от Platega: {status}")

    if status == "confirmed":
        # 🔒 Защита от двойного начисления
        if payment['status'] == 'confirmed':
            await safe_edit(query, "✅ Платёж уже обработан ранее.")
            return

        package_key = payment['package_key']
        pkg = get_package(package_key)
        if not pkg:
            logger.error(f"❌ Пакет '{package_key}' из БД не найден в конфиге!")
            await safe_edit(query, "❌ Ошибка конфигурации. Напишите админу.")
            return

        credits_to_add = pkg["credits"]

        # ✅ Обновляем статус в БД
        confirmed = await confirm_payment(payment_id, credits_to_add)
        if not confirmed:
            await safe_edit(query, "✅ Платёж уже обработан.")
            return

        # 💰 Начисляем через твою функцию
        await add_paid_credits(payment['user_id'], credits_to_add)

        # 🎉 Уведомляем
        await safe_edit(
            query,
            f"✅ **Оплата подтверждена!**\n"
            f"🎁 Начислено: `{credits_to_add}` генераций.\n"
            f"🔖 ID транзакции (Platega): `{payment['transaction_id']}`\n"
            f"✨ Спасибо! `/gen`",
            parse_mode="Markdown"
        )

    elif status == "pending":
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Проверить ещё раз", callback_data=query.data)
        ], [
            InlineKeyboardButton("↩️ Назад", callback_data="main_menu")
        ]])
        await safe_edit(
            query,
            "⏳ Платёж ещё обрабатывается. Обычно 1-2 минуты.\n"
            "Нажми кнопку ниже, когда оплата пройдёт.",
            reply_markup=kb
        )
    elif status == "canceled":
        await safe_edit(query, "❌ Платёж отменён. Попробуйте `/buy` снова.")
    elif status == "chargebacked":
        await safe_edit(query, "⚠️ Платёж оспорен. Напишите админу.")
    else:
        await safe_edit(query, "❓ Не удалось определить статус. Напишите админу.")