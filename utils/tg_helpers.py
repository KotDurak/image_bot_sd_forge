from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message
import logging

logger = logging.getLogger(__name__)

async def send_image_with_actions(
    message: Message,
    image_bytes: bytes,
    caption: str,
    **kwargs
):
    """Отправляет фото без кнопок (просто и надёжно)"""
    await message.reply_photo(
        photo=image_bytes,
        caption=caption,
        api_kwargs={"read_timeout": 30}
    )