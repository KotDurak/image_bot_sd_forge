from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
from models.ads import confirm_ad_delivery, fetch_pending_ad
import asyncio
import logging


logger = logging.getLogger(__name__)


async def show_ad_after_generation(message: Message, gen_id: int):
    """
    Показывает рекламу после генерации.
    Списывает показ ТОЛЬКО при успешной отправке.
    """
    ad = await fetch_pending_ad()
    if not ad:
        return

    keyboard = [[InlineKeyboardButton(ad["btn_text"], url=ad["target_link"])]]
    markup = InlineKeyboardMarkup(keyboard)

    try:
        if ad["ad_type"] == "photo":
            await message.reply_photo(
                photo=ad["content"],
                caption="✨ Генерация завершена! А пока вы ждали, вот интересное:",
                reply_markup=markup
            )
        else:
            await message.reply_text(
                text=ad["content"],
                reply_markup=markup
            )

        # ✅ Успех — списываем показ
        await confirm_ad_delivery(ad["id"], gen_id)

    except Exception as e:
        logger.warning(f"⚠️ Реклама #{ad['id']} не показана: {e}")

