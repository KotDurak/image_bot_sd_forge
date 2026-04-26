from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, \
    PreCheckoutQueryHandler
from telegram import Update
from telegram.request import HTTPXRequest
from handlers import payments, commands, callbacks, presets, admins
from db.async_core import async_db
from services.queue_manager import GenerationQueue
import config
import logging
import asyncio
from utils.logger import setup_logging
setup_logging(config.MODE, logs_dir=config.LOGS_DIR)
queue_manager = GenerationQueue()

logger = logging.getLogger(__name__)

async def post_init(app: Application):
    """Асинхронная инициализация: БД, очередь, логирование"""
    await async_db.init()
    logger.info("🔌 БД подключена (aiosqlite)")

    await queue_manager.start()
    logger.info("🚀 Очередь генерации запущена")

    logger.info("🤖 Бот запущен и готов к творчеству!")


async def post_shutdown(app: Application):
    """Асинхронная очистка при завершении"""
    logger.info("🧹 Корректное завершение работы...")

    await queue_manager.stop()
    await async_db.close()

    logger.info("✅ Бот остановлен. Коты довольны.")


async def generate_with_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wrapper для передачи queue_manager в handler"""
    # Создаём корутину и планируем её выполнение
    asyncio.create_task(commands.generate(update, context, queue_manager))


def register_handlers(app: Application):
    """Регистрирует все обработчики"""
    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CommandHandler("gen", generate_with_queue))
    app.add_handler(CommandHandler("help", callbacks.help_cmd))
    app.add_handler(CommandHandler("preset", commands.preset_command))
    app.add_handler(CommandHandler("cancel", presets.cancel_wizard))
    app.add_handler(CommandHandler("model", commands.model_command))
    app.add_handler(CommandHandler("settings", commands.settings_command))
    app.add_handler(CommandHandler("history", commands.history_cmd))

    app.add_handler(CallbackQueryHandler(callbacks.select_model_callback, pattern="^select_model$|^model_"))
    app.add_handler(CallbackQueryHandler(presets.preset_router, pattern="^preset|^presets"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, presets.handle_wizard_text))
    app.add_handler(CallbackQueryHandler(callbacks.settings_callback, pattern="^settings$"))
    app.add_handler(CallbackQueryHandler(callbacks.main_menu_callback, pattern="^main_menu$"))

    # admin
    app.add_handler(CommandHandler("unlimited", admins.unlimited_cmd))
    app.add_handler(CommandHandler("ban", admins.ban_cmd))
    app.add_handler(CommandHandler("reset", admins.reset_cmd))
    app.add_handler(CommandHandler('add_credits', admins.debug_add_credits))

    # 💰 Платежи
    app.add_handler(CommandHandler("buy", payments.buy_credits_cmd))
    app.add_handler(CallbackQueryHandler(payments.process_purchase_callback, pattern="^buy_"))
    app.add_handler(CommandHandler("balance", payments.balance_cmd))
    app.add_handler(CommandHandler("report", payments.report_cmd))

    # ⭐ Обязательные хендлеры для Telegram Payments API
    app.add_handler(PreCheckoutQueryHandler(payments.pre_checkout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, payments.successful_payment_callback))


def main():
    """Точка входа — синхронная, без asyncio.run()"""

    app = Application.builder() \
        .token(config.TELEGRAM_TOKEN) \
        .request(HTTPXRequest(connect_timeout=10, read_timeout=20)) \
        .post_init(post_init) \
        .post_shutdown(post_shutdown) \
        .build()

    register_handlers(app)

    try:
        # ✅ БЛОКИРУЮЩИЙ вызов — НЕ await!
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Глобальная ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    main()