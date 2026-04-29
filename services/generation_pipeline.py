"""Пайплайн генерации: проверка лимитов, отправка в очередь."""
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.queue_manager import QueueItem
from services.forge_api import call_forge_api
from models.user_quota import check_generation_limit, increment_usage
import config

logger = logging.getLogger(__name__)


async def check_user_limits(update: Update, user_id: int) -> str | None:
    """
    Проверяет квоты пользователя.
    Возвращает usage_type ('free'/'ok') или None (если лимит превышен и ответ уже отправлен).
    """
    allowed, reason = await check_generation_limit(user_id)
    if not allowed:
        if reason == 'no_credits':
            await update.message.reply_text(
                "⚠️ Лимит исчерпан. Пополни счёт или подожди обновления.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🛒 Пополнить", callback_data="buy_starter")
                ]])
            )
        else:
            await update.message.reply_text(reason)
        return None
    return reason


async def submit_to_queue(
    user_id: int,
    prompt: str,
    payload: dict,
    settings: dict,
    update: Update,
    progress_msg,
    queue_manager,
    usage_type: str
) -> None:
    """Собирает QueueItem и ставит в очередь."""
    is_free = usage_type in ["free", "ok"]
    show_ads = config.ADS_ENABLED and (
        is_free or (not is_free and random.random() < config.ADS_PAID_CHANCE)
    )

    queue_item = QueueItem(
        user_id=user_id,
        prompt=prompt,
        payload=payload,
        message=update.message,
        progress_msg=progress_msg,
        callback=call_forge_api,
        usage_type=usage_type,
        preset_used=settings.get("preset"),
        show_ads=show_ads
    )
    await queue_manager.add_request(queue_item)
    await increment_usage(user_id, usage_type=usage_type)