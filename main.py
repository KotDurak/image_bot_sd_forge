import asyncio
import logging
import time
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram import Update
from telegram.request import HTTPXRequest
from database import init_db, close_db
import config
from utils.logger import setup_logging
from handlers import commands, callbacks, presets, admins
from services.queue_manager import GenerationQueue
import signal
import sys
from pathlib import Path

# ─── Настройка окружения ─────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
setup_logging()
logger = logging.getLogger(__name__)

queue_manager = GenerationQueue()
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
    app.add_handler(CommandHandler("preset", commands.preset_command))
    app.add_handler(CommandHandler("cancel", presets.cancel_wizard))
    app.add_handler(CommandHandler("model", commands.model_command))
    app.add_handler(CommandHandler("settings", commands.settings_command))

    app.add_handler(CallbackQueryHandler(callbacks.select_model_callback, pattern="^select_model$|^model_"))

    # Один роутер ловит ВСЕ кнопки, начинающиеся с preset или presets
    app.add_handler(CallbackQueryHandler(presets.preset_router, pattern="^preset|^presets"))

    # ТЕКСТ В МАСТЕРЕ (срабатывает только если user_id в _wizard_state)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, presets.handle_wizard_text))

    app.add_handler(CallbackQueryHandler(callbacks.settings_callback, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(callbacks.main_menu_callback, pattern="^main_menu$"))

    #admin
    app.add_handler(CommandHandler("unlimited", admins.unlimited_cmd))
    app.add_handler(CommandHandler("ban", admins.ban_cmd))
    app.add_handler(CommandHandler("reset", admins.reset_cmd))


# ─── Асинхронный цикл бота ───────────────────────────────────────────────────
async def run_bot():
    """Запуск бота с корректной инициализацией и обработкой сигналов"""

    # 1. Настраиваем приложение
    app = Application.builder() \
        .token(config.TELEGRAM_TOKEN) \
        .request(HTTPXRequest(connect_timeout=10, read_timeout=20)) \
        .build()

    register_handlers(app)

    # 2. Запускаем зависимые сервисы
    await queue_manager.start()
    logger.info("🤖 Бот запущен и готов к творчеству!")

    try:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        # Держим бота запущенным (элегантнее, чем while True)
        await asyncio.Event().wait()

    except asyncio.CancelledError:
        logger.info("🛑 Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка в боте: {e}", exc_info=True)
        raise
    finally:
        logger.info("🧹 Корректное завершение работы...")
        # Останавливаем в обратном порядке
        if app.updater and app.updater.running:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await queue_manager.stop()
        close_db()
        logger.info("✅ Бот остановлен. Коты довольны.")


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