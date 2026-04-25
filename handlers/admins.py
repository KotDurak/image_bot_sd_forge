from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import config
from models.user_quota import grant_unlimited, ban_user, reset_usage
import logging

logger = logging.getLogger(__name__)

async def unlimited_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/unlimited <user_id> — выдать/забрать безлимит"""
    if update.effective_user.id not in config.ADMINS:  # твой список админов
        return

    if not context.args:
        await update.message.reply_text("Используй: `/unlimited 8039643413`")
        return

    try:
        target_id = int(context.args[0])
        await grant_unlimited(target_id, grant=True)
        await update.message.reply_text(f"✅ Безлимит выдан user_{target_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/ban <user_id> — забанить пользователя"""

    # Проверка прав админа
    if update.effective_user.id not in config.ADMINS:
        await update.effective_message.reply_text("🔒 Только для админов.")
        return

    if not context.args:
        await update.effective_message.reply_text("Используй: `/ban 123456789`")
        return

    try:
        target_id = int(context.args[0])
        # Если второй аргумент не '0', 'false', 'no' — баним, иначе разбаниваем
        ban = len(context.args) < 2 or context.args[1].lower() not in ('0', 'false', 'no')

        # Выполняем бан/разбан
        await ban_user(target_id, ban)
        ban_info = 'забанен' if ban else 'разбанен'

        # 🔥 Безопасный ответ: проверяем, что сообщение существует
        if update.effective_message:
            await update.effective_message.reply_text(f"🔒 user_{target_id} {ban_info}.")
        else:
            # Логируем на случай, если не смогли ответить
            logger.info(f"🔒 user_{target_id} {ban_info} (ответ не отправлен: message=None)")

    except ValueError:
        if update.effective_message:
            await update.effective_message.reply_text("❌ Неверный user_id")
        else:
            logger.error(f"❌ Неверный user_id в /ban от user_{update.effective_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в /ban: {e}", exc_info=True)
        if update.effective_message:
            await update.effective_message.reply_text("❌ Внутренняя ошибка. Проверь логи.")


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset <user_id> — сбросить счётчик (для тестов)"""
    if update.effective_user.id not in config.ADMINS:
        return

    if not context.args:
        await update.message.reply_text("Используй: `/reset 123456789`")
        return

    try:
        target_id = int(context.args[0])
        await reset_usage(target_id)
        await update.message.reply_text(f"🔄 Счётчик сброшен для user_{target_id}")
    except ValueError:
        await update.message.reply_text("❌ Неверный user_id")