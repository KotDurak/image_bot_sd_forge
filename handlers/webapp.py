import json
import logging
from telegram import Update
from telegram.ext import ContextTypes

from handlers import commands

logger = logging.getLogger(__name__)


async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        raw_data = update.message.web_app_data.data
        data = json.loads(raw_data)

        if data.get("action") == "generate_from_webapp":
            raw_prompt = data.get("prompt", "").strip()
            overrides = data.get("overrides", {})  # <-- Достаем словарь

            logger.info(f"📥 Web App: получены теги. Overrides: {overrides}")

            if not raw_prompt:
                await update.effective_message.reply_text("❌ Промпт пустой.")
                return

            await update.effective_message.reply_text("⏳ Промпт получен! Ставлю в очередь...")

            queue_manager = context.bot_data.get('queue_manager')
            if not queue_manager:
                raise RuntimeError("Очередь генерации не найдена.")

            await commands.generate(
                update=update,
                context=context,
                queue_manager=queue_manager,
                custom_prompt=raw_prompt,
                overrides=overrides  # <-- Передаем словарь в generate
            )

    except json.JSONDecodeError:
        logger.error("❌ Ошибка парсинга JSON из Web App")
    except Exception as e:
        logger.error(f" Ошибка в webapp: {e}", exc_info=True)
        await update.effective_message.reply_text(f"❌ Ошибка: {str(e)}")