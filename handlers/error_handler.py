import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def global_error_handler(update: Update | None, context: ContextTypes.DEFAULT_TYPE):
    """Ловит все необработанные исключения и пишет их в лог, а не в консоль"""
    error = context.error

    # Логируем с контекстом
    chat_id = getattr(update, "effective_chat", None)
    user_id = getattr(update.effective_user, "id", None) if update else None

    logger.error(
        f"💥 Unhandled error | chat={chat_id.id if chat_id else 'N/A'} | user={user_id} | {error}",
        exc_info=error
    )

    # Опционально: уведомить юзера (чтобы не зависал с "бесконечной загрузкой")
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "😿 Что-то пошло не так. Попробуй позже или напиши /help",
                reply_to_message_id=update.effective_message.message_id
            )
        except Exception:
            pass  # Если и это упало — пусть лучше тишина, чем двойной краш