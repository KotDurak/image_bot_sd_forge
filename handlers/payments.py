from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import logging
from pricing import PACKAGES, get_package

logger = logging.getLogger(__name__)

async def buy_credits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /buy — меню покупки пакетов"""
    keyboard = []
    for key, pkg in PACKAGES.items():
        # Пропускаем тестовый пакет в продакшен-меню (оставляем только для админов/тестов)
        #if key == "test_1":
            #continue
        keyboard.append([
            InlineKeyboardButton(
                f"{pkg['label']} — {pkg['stars']} ⭐",
                callback_data=f"buy_{key}"
            )
        ])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="main_menu")])

    await update.message.reply_text(
        "🛒 **Купить генерации**\n"
        "Оплата через Telegram Stars ⭐\n"
        "_Кредиты начисляются мгновенно после подтверждения платежа_",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def process_purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    package_key = query.data.replace("buy_", "")
    pkg = get_package(package_key)

    if not pkg:
        await query.edit_message_text("❌ Пакет не найден. Попробуйте /buy")
        return

    # Формируем payload с безопасным разделителем
    payload = f"credits:{package_key}:{query.from_user.id}"

    # Отправляем инвойс
    await query.message.reply_invoice(
        title="🎨 Генерация изображений",
        description=f"{pkg['label']}\n{pkg['desc']}",
        payload=payload,
        provider_token="",  # ⭐ Для Stars всегда пустая строка
        currency="XTR",
        prices=[LabeledPrice(label="Кредиты", amount=pkg["stars"])],
        max_tip_amount=0,
        need_name=False,
        need_email=False,
        need_phone_number=False,
        need_shipping_address=False,
        is_flexible=False,
    )

async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение перед списанием (обязательный хендлер)"""
    query = update.pre_checkout_query
    # Проверяем валидность платежа (можно добавить доп. проверки)
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка успешной оплаты"""
    payment = update.message.successful_payment
    user_id = update.effective_user.id

    try:
        parts = payment.invoice_payload.split(":")
        if len(parts) != 3:
            raise ValueError(f"Неверный формат payload: {payment.invoice_payload}")

        _, package_key, payload_user_id = parts

        if int(payload_user_id) != user_id:
            raise ValueError("User ID mismatch в payload")

    except Exception as e:
        logger.error(f"❌ Ошибка парсинга payload: {e} | raw: {payment.invoice_payload}")
        await update.message.reply_text("❌ Ошибка обработки платежа. Обратитесь к админу.")
        return

    # 🔥 Берём данные из pricing.py
    pkg = get_package(package_key)
    if not pkg:
        logger.warning(f"⚠️ Неизвестный пакет в оплате: {package_key}")
        await update.message.reply_text("❌ Пакет не найден. Напишите админу.")
        return

    credits_to_add = pkg["credits"]

    # 1️⃣ Начисляем кредиты
    from models.user_quota import add_paid_credits
    await add_paid_credits(user_id, credits_to_add)

    # 2️⃣ Логируем покупку в БД
    from db.async_core import async_db
    await async_db.conn.execute(
        """INSERT INTO star_payments 
           (user_id, payment_id, stars_amount, credits_granted, currency)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, payment.provider_payment_charge_id,
         payment.total_amount, credits_to_add, payment.currency)
    )
    await async_db.conn.commit()

    # 3️⃣ Уведомляем пользователя
    await update.message.reply_text(
        f"✅ Оплата прошла успешно!\n"
        f"🎁 Начислено: `{credits_to_add}` генераций.\n"
        f"✨ Спасибо за поддержку! `/gen`",
        parse_mode="Markdown"
    )


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from models.user_quota import get_quota_balance  # создадим ниже

    free, paid, total = await get_quota_balance(user_id)
    status = "✅" if total > 0 else "⚠️"
    text = (
        f"{status} **Ваш баланс генераций**\n\n"
        f"🆓 Бесплатные: `{free}`\n"
        f"⭐ Платные: `{paid}`\n"
        f"🎯 Всего доступно: `{total}`\n\n"
        f"💡 Пополнить: /buy\n"
        f"🎨 Сгенерировать: /gen"
    )
    for k, v in list(PACKAGES.items())[1:3]:  # первые 2 не-тестовых
        text += f"• {v['label']} за {v['stars']} ⭐\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from db.async_core import async_db

    # Логируем в БД или файл
    await async_db.conn.execute(
        """INSERT INTO generation_requests 
           (user, prompt, model_used, status, error_message, created_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (str(user_id), "USER_REPORT", "UNKNOWN", "failed", "Пользователь сообщил о списании без результата")
    )
    await async_db.conn.commit()

    await update.message.reply_text(
        "📝 Заявка принята. Админ проверит логи и вернёт баланс, если подтвердится ошибка.\n"
        "Обычно это занимает 10-15 минут. Спасибо за терпение! 🐾"
    )