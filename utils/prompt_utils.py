"""Утилиты для работы с промптами: извлечение, перевод, валидация."""
import re
from telegram import Update
from telegram.ext import ContextTypes
from utils.translate import translate_prompt_free

logger = __import__("logging").getLogger(__name__)

CYRILLIC_RE = re.compile(r'[а-яА-ЯёЁ]')


def extract_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """
    Извлекает текст промпта из команды /gen.
    Возвращает строку или None (если промпт пуст).
    """
    if context.args:
        return " ".join(context.args)

    text = update.message.text
    return text.replace("/gen", "", 1).strip() or None


async def prepare_prompt(update: Update, raw_prompt: str) -> str | None:
    """
    Проверяет на кириллицу и переводит при необходимости.
    Возвращает готовый английский промпт или None (с отправкой уведомления).
    """
    if not CYRILLIC_RE.search(raw_prompt):
        return raw_prompt

    translated = await translate_prompt_free(raw_prompt)

    if not CYRILLIC_RE.search(translated):
        return translated

    await update.message.reply_text(
        "🇷🇺 Нейросети не понимают русский. Переведи промпт на английский (Google, DeepL, Яндекс)\n"
        "💡 Пример: `cat stealing ham, cinematic lighting, photorealistic`",
        parse_mode="Markdown"
    )
    return None