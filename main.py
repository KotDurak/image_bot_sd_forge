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
import os

if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    # Для консоли (если запускаешь не как службу)
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

def _graceful_shutdown(signum, frame):
    """Корректное завершение при Ctrl+C, kill, выключении ПК"""
    logger.info(f"📡 Получен сигнал {signum}. Останавливаем бота и закрываем БД...")
    from database import db, close_db
    try:
        close_db()
    except Exception:
        pass
    sys.exit(0)


setup_logging()
logger = logging.getLogger(__name__)

queue_manager: GenerationQueue = None

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


def main():
    global queue_manager
    init_db()
    # Инициализируем очередь
    queue_manager = GenerationQueue(max_concurrent=1)

    app = (Application.builder()
           .request(
        HTTPXRequest(
            connect_timeout=30,  # ⏱ Подключение: 30 сек
            read_timeout=60,  # ⏱ Чтение ответа: 60 сек
            write_timeout=60,  # ⏱ Отправка данных: 60 сек
            pool_timeout=30  # ⏱ Ожидание свободного соединения
        )
    )
       .token(config.TELEGRAM_TOKEN).build())

    register_handlers(app)

    logger.info("🤖 Бот запущен и готов к творчеству!")

    # Запускаем бота и очередь
    async def run_bot():
        await queue_manager.start()
        try:
            await app.initialize()
            await app.start()
            if app.updater:
                await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                # Держим бота запущенным
                while True:
                    await asyncio.sleep(1)
        finally:
            await queue_manager.stop()
            if app.updater:
                await app.updater.stop()
            await app.stop()
            close_db()
            await app.shutdown()

    # Запускаем в event loop
    asyncio.run(run_bot())


if __name__ == "__main__":
    restart_count = 0
    while True:
        try:
            main()
            restart_count = 0
        except Exception as e:
            restart_count += 1
            logger.error(f"🔥 Краш #{restart_count}: {e}", exc_info=True)
            if restart_count > 5:
                logger.critical("💀 Слишком много падений. Ждём 60 сек...")
                time.sleep(60)
            else:
                time.sleep(5)