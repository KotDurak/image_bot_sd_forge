import logging
import sys
from pathlib import Path

# Добавляем корень проекта в PATH, чтобы работали импорты типа `from db.async_core`
project_root = Path(__file__).resolve().parents[1]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from db.async_core import async_db  # noqa: E402

# Настройка логгера: и в консоль, и в файл (важно для Windows Scheduler)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    # Консольный вывод (для отладки)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    logger.addHandler(ch)

    # Файловый лог (обязательно для фоновых задач)
    log_file = project_root / "logs" / "cron_reset_quota.log"
    log_file.parent.mkdir(exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh.setFormatter(formatter)
    logger.addHandler(fh)


async def reset_daily_free_limits() -> int:
    """Ежедневный сброс остатков бесплатных генераций до 2."""
    # 🔑 Инициализируем соединение с БД (если ещё не инициализировано)
    if not hasattr(async_db, "_initialized") or not async_db._initialized:
        await async_db.init()  # ← Если init() требует аргументов (например, db_path) — укажите их здесь
        async_db._initialized = True  # флаг, чтобы не инициализировать повторно

    try:
        await async_db.conn.execute("BEGIN TRANSACTION")
        cursor = await async_db.conn.execute("""
            UPDATE user_quota 
            SET free_used = free_limit - 2, 
                last_reset = CURRENT_TIMESTAMP
            WHERE (free_limit - free_used) < 2 
              AND free_limit >= 2
              AND is_banned = 0 
              AND is_unlimited = 0
        """)
        await async_db.conn.commit()
        updated_count = cursor.rowcount
        logger.info(f"✅ Сброс лимитов завершён: обновлено {updated_count} пользователей.")
        return updated_count
    except Exception as e:
        # Безопасный rollback: только если соединение точно есть
        try:
            await async_db.conn.rollback()
        except:
            pass  # Игнорируем ошибки отката, если соединение не открыто
        logger.error(f"❌ Ошибка при сбросе лимитов: {e}", exc_info=True)
        raise
    finally:
        # Безопасное закрытие: проверяем, что conn существует и открыт
        try:
            if hasattr(async_db, "conn") and async_db.conn:
                await async_db.conn.close()
        except:
            pass  # Игнорируем ошибки закрытия, чтобы не маскировать основную ошибку


if __name__ == "__main__":
    """
    Точка входа для запуска через планировщик:
    python -m cron.reset_quota
    или
    python cron/reset_quota.py
    """
    import asyncio

    logger.info("🚀 Запуск задачи reset_daily_free_limits...")
    try:
        result = asyncio.run(reset_daily_free_limits())
        logger.info(f"✨ Задача завершена. Затронуто строк: {result}")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка выполнения: {e}", exc_info=True)
        sys.exit(1)