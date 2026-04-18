import asyncio
import logging
import time
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram import Update
from telegram.request import HTTPXRequest
from database import init_db, close_db
import config
from utils.logger import setup_logging
from handlers import commands, callbacks
from services.queue_manager import GenerationQueue
import signal
import sys
from pathlib import Path

# ─── Настройка окружения ─────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
setup_logging()
logger = logging.getLogger(__name__)

queue_manager = GenerationQueue(max_concurrent=1)
app = None

async def generate_with_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper для передачи queue_manager в handler"""
    await commands.generate(update, context, queue_manager)

def register_handlers(app: Application):
    """Регистрирует все обработчики"""
    # Команды
    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CommandHandler("gen", generate_with_queue))
    app.add_handler(CommandHandler("help", callbacks.help_cmd))
    app.add_handler(CommandHandler("preset", commands.preset_command))  # нужно добавить в commands
    app.add_handler(CommandHandler("model", commands.model_command))    # нужно добавить в commands
    app.add_handler(CommandHandler("settings", commands.settings_command))

    # Callbacks
    app.add_handler(CallbackQueryHandler(callbacks.select_model_callback, pattern="^select_model$|^model_"))
    app.add_handler(CallbackQueryHandler(callbacks.presets_callback, pattern="^presets$"))
    app.add_handler(CallbackQueryHandler(callbacks.apply_preset_callback, pattern="^preset_"))
    app.add_handler(CallbackQueryHandler(callbacks.settings_callback, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(callbacks.main_menu_callback, pattern="^main_menu$"))


# ─── Асинхронный цикл бота ───────────────────────────────────────────────────
async def run_bot():
    await queue_manager.start()
    logger.info("🤖 Бот запущен и готов к творчеству!")

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("🛑 Получен сигнал остановки")
    finally:
        logger.info("🧹 Корректное завершение работы...")
        if app.updater and app.updater.running:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await queue_manager.stop()
        close_db()
        logger.info("✅ Бот остановлен. Коты довольны.")

async def run_bot():
    # Настраиваем приложение
    app = Application.builder() \
        .token(config.TELEGRAM_TOKEN) \
        .request(HTTPXRequest(connect_timeout=10, read_timeout=20)) \
        .build()

    register_handlers(app)


    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()  # Держим бота запущенным


def main():
    init_db()

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        pass  # Нормальный выход
    except Exception as e:
        logger.error(f"Глобальная ошибка: {e}")


if __name__ == "__main__":
    main()