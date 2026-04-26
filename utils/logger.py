"""
🐱 Логирование для бота
Режимы:
  - DEV: "Пушок, исследуй лапками каждое отверстие" → полный отладочный вывод
  - PROD: "Пушок, не разбрасывай всюду мышки пищалки" → только ошибки и важное
"""
import logging
import logging.handlers
from pathlib import Path

# 🎚 Уровни логирования по модулям для PROD
_PROD_LOG_LEVELS = {
    # 🔇 Внешние библиотеки — только критические ошибки
    "telegram": logging.ERROR,
    "telegram.ext": logging.ERROR,
    "httpx": logging.ERROR,
    "urllib3": logging.ERROR,

    # 🎯 Наши сервисы — только ошибки (генерация долгая, детали — в метрики)
    "services.queue_manager": logging.ERROR,
    "services.forge_api": logging.ERROR,

    # 💰 Платежи и квоты — оставляем INFO для аудита
    "handlers.payments": logging.INFO,
    "models.user_quota": logging.INFO,

    # 🗄 База данных — только ошибки соединения/записи
    "db.async_core": logging.ERROR,

    # 🎮 Хендлеры команд — только ошибки (действия юзеров — не в лог)
    "handlers.commands": logging.ERROR,
    "handlers.callbacks": logging.ERROR,
    "handlers.presets": logging.ERROR,
    "handlers.admins": logging.ERROR,
}


def setup_logging(mode: str = "PROD", logs_dir: Path | str = "logs") -> None:
    """
    Настраивает логирование под режим.

    🐾 Режимы:
        - "DEV": Пушок, исследуй лапками каждое отверстие
          → DEBUG в консоль, всё видно, без ротации

        - "PROD": Пушок, не разбрасывай всюду мышки пищалки  
          → только ошибки в файл + консоль, ротация 10MB × 3

    Args:
        mode: "DEV" или "PROD" (регистр не важен)
        logs_dir: путь к папке для логов
    """
    mode = mode.upper()
    logs_path = Path(logs_dir)
    logs_path.mkdir(exist_ok=True)

    if mode == "DEV":
        # 🔍 DEV: полная отладка, всё в консоль
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%H:%M:%S",
            handlers=[logging.StreamHandler()],
            force=True  # Перезаписать предыдущую конфигурацию, если есть
        )
        _mode_emoji = "🔧"
        _mode_desc = "DEV: Пушок, исследуй лапками каждое отверстие"

    else:  # PROD
        # 🚀 PROD: тихо, чисто, только важное
        logging.basicConfig(
            level=logging.WARNING,  # База: скрываем INFO
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            handlers=[
                # 📁 Файл с ротацией: 10 MB, хранить 3 последних
                logging.handlers.RotatingFileHandler(
                    logs_path / "bot.log",
                    maxBytes=10 * 1024 * 1024,
                    backupCount=3,
                    encoding="utf-8",
                    delay=True
                ),
                # 💻 Консоль: только ошибки (для pm2 / systemd)
                logging.StreamHandler()
            ],
            force=True
        )

        # 🔇 Применяем тонкую настройку по модулям
        for logger_name, level in _PROD_LOG_LEVELS.items():
            logging.getLogger(logger_name).setLevel(level)

        _mode_emoji = "🚀"
        _mode_desc = "PROD: Пушок, не разбрасывай всюду мышки пищалки"

    # 🐾 Финальное подтверждение
    root_logger = logging.getLogger(__name__)
    root_logger.info(f"{_mode_emoji} Логирование: {_mode_desc}")


__all__ = ["setup_logging"]