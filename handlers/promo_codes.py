# handlers/promo_codes.py
import logging
from telegram import Update
from telegram.ext import ContextTypes, filters
import config  # Предполагаем, что тут есть ADMINS, как в твоем примере с ad_management

from models.promo_codes import create_promo_code, get_promo_code, activate_promo_code, get_or_create_user_referral_code

logger = logging.getLogger(__name__)


async def promo_activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /promo <код> для активации промокода пользователем."""
    user = update.effective_user
    user_id = user.id

    if not context.args:
        await update.message.reply_text(
            "🎟 Чтобы активировать промокод, напиши его после команды через пробел.\n\n"
            "Пример: <code>/promo GIFT2024</code>",
            parse_mode="HTML"
        )
        return

    promo_code_input = context.args[0]

    await update.message.reply_text("⏳ Проверяю промокод...")

    result = await activate_promo_code(user_id, promo_code_input)

    if result["success"]:
        await update.message.reply_text(result["message"])
        logger.info(f"✅ Юзер {user_id} (@{user.username}) активировал промокод {promo_code_input}")
    else:
        await update.message.reply_text(result["message"])
        logger.warning(
            f"⚠️ Юзер {user_id} (@{user.username}) не смог активировать промокод {promo_code_input}: {result['message']}")


async def create_promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Админская команда для создания промокода.
    Использование: /create_promo <CODE> <paid_credits> <free_limit> [max_uses]
    Пример: /create_promo GIFT2024 10 5 100
    """
    user = update.effective_user
    if user.id not in config.ADMINS:
        logger.warning(f"⛔ Неавторизованная попытка создания промокода от юзера {user.id}")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Использование: <code>/create_promo &lt;КОД&gt; &lt;paid_credits&gt; &lt;free_limit&gt; [max_uses]</code>\n"
            "Пример: <code>/create_promo NEWYEAR 10 5 100</code>\n"
            "(max_uses необязательно, по умолчанию безлимит)",
            parse_mode="HTML"
        )
        return

    code = context.args[0].upper()
    try:
        paid_credits = int(context.args[1])
        free_limit = int(context.args[2])
        max_uses = int(context.args[3]) if len(context.args) > 3 else None
    except ValueError:
        await update.message.reply_text("❌ Ошибка: paid_credits, free_limit и max_uses должны быть целыми числами.")
        return

    success = await create_promo_code(
        code=code,
        bonus_paid_credits=paid_credits,
        bonus_free_limit=free_limit,
        max_uses=max_uses,
        created_by=user.id
    )

    if success:
        msg = (
            f"✅ Промокод <code>{code}</code> успешно создан!\n\n"
            f"💳 Paid credits: +{paid_credits}\n"
            f"🎁 Free limit: +{free_limit}\n"
            f"🔢 Макс. использований: {max_uses if max_uses else 'Безлимит'}"
        )
        await update.message.reply_text(msg, parse_mode="HTML")
        logger.info(f"🛠 Админ {user.id} создал промокод {code}")
    else:
        await update.message.reply_text(
            f"❌ Не удалось создать промокод. Возможно, код <code>{code}</code> уже существует.", parse_mode="HTML")


async def promo_stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Админская команда для просмотра статистики промокода.
    Использование: /promo_stats <CODE>
    """
    user = update.effective_user
    if user.id not in config.ADMINS:
        return

    if not context.args:
        await update.message.reply_text("⚠️ Использование: <code>/promo_stats &lt;КОД&gt;</code>", parse_mode="HTML")
        return

    code = context.args[0].upper()
    promo = await get_promo_code(code)

    if not promo:
        await update.message.reply_text(f"❌ Промокод <code>{code}</code> не найден.", parse_mode="HTML")
        return

    status = "🟢 Активен" if promo["is_active"] else "🔴 Деактивирован"
    uses_info = f"{promo['current_uses']} из {promo['max_uses']}" if promo[
        'max_uses'] else f"{promo['current_uses']} (безлимит)"

    msg = (
        f"📊 Статистика промокода <code>{promo['code']}</code>\n\n"
        f"Статус: {status}\n"
        f"💳 Paid credits за активацию: {promo['bonus_paid_credits']}\n"
        f"🎁 Free limit за активацию: {promo['bonus_free_limit']}\n"
        f"🔢 Использований: {uses_info}\n"
        f"📅 Создан: {promo['created_at']}"
    )

    await update.message.reply_text(msg, parse_mode="HTML")


async def my_referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /my_referral — показывает пользователю его персональный реферальный код."""
    user = update.effective_user
    user_id = user.id

    code = await get_or_create_user_referral_code(user_id)

    await update.message.reply_text(
        f"🎟 <b>Твой реферальный промокод:</b>\n\n"
        f"<code>{code}</code>\n\n"
        f"Поделись им с друзьями! Когда они введут этот код и сгенерируют "
        f"хотя бы одно изображение, ты получишь бонусные кредиты. 🎁",
        parse_mode="HTML"
    )