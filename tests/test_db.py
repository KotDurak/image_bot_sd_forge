# stress_test_db.py
import asyncio
import logging
import shutil
import time
import os
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Импортируем наш async_db (убедись, что путь верный)
import sys

sys.path.insert(0, str(Path(__file__).parent))
from db.async_core import AsyncDB

# ─────────────────────────────────────────────────────────────
# Конфигурация теста
# ─────────────────────────────────────────────────────────────
TEST_DB_PATH = "bot_data_stress_test.db"
ORIGINAL_DB_PATH = "../bot_data.db"
CONCURRENT_USERS = 50
REQUESTS_PER_USER = 10
BATCH_SIZE = 10  # Сколько запросов выполнять параллельно внутри одного "пользователя"


async def simulate_user(db: AsyncDB, user_id: int, requests_count: int):
    """
    Эмулирует активность пользователя:
    - Чтение настроек
    - Обновление настроек
    - Логирование генерации
    - Инкремент счётчика
    """
    for req in range(requests_count):
        try:
            # 1. Чтение (не блокирует)
            cursor = await db.conn.execute(
                "SELECT model, preset, requests_count FROM user_settings WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()

            # 2. Обновление (требует коммита)
            await db.conn.execute(
                "UPDATE user_settings SET requests_count = requests_count + 1, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (user_id,)
            )
            await db.conn.commit()

            # 3. Логирование генерации (вставка)
            await db.conn.execute(
                """INSERT INTO generation_requests 
                   (user, prompt, model_used, status, created_at) 
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (str(user_id), f"stress_test_prompt_{req}", "test_model.safetensors", "completed")
            )
            await db.conn.commit()

        except Exception as e:
            logger.error(f"❌ User {user_id}, req {req}: {e}")
            raise

        # Небольшая пауза для реалистичности
        await asyncio.sleep(0.01)

    logger.debug(f"✅ User {user_id} completed {requests_count} requests")


async def run_stress_test():
    """Запускает стресс-тест БД"""

    # 1. Подготовка: копируем БД, чтобы не портить основную
    if not Path(ORIGINAL_DB_PATH).exists():
        logger.error(f"❌ Исходная БД не найдена: {ORIGINAL_DB_PATH}")
        return

    logger.info(f"📦 Копируем БД: {ORIGINAL_DB_PATH} → {TEST_DB_PATH}")
    shutil.copy2(ORIGINAL_DB_PATH, TEST_DB_PATH)

    # 2. Инициализируем тестовую БД
    db = AsyncDB(TEST_DB_PATH)
    await db.init()
    logger.info("🔌 Тестовая БД подключена")

    # 3. Запускаем нагрузку
    start_time = time.time()
    total_requests = CONCURRENT_USERS * REQUESTS_PER_USER

    logger.info(f"🚀 Старт: {CONCURRENT_USERS} пользователей × {REQUESTS_PER_USER} запросов = {total_requests} операций")

    # Создаём задачи с ограничением параллелизма (semaphore)
    semaphore = asyncio.Semaphore(BATCH_SIZE)

    async def wrapped_user(uid):
        async with semaphore:
            await simulate_user(db, uid, REQUESTS_PER_USER)

    tasks = [wrapped_user(10000 + i) for i in range(CONCURRENT_USERS)]

    # Выполняем и собираем результаты
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = time.time() - start_time

    # 4. Анализируем результаты
    errors = sum(1 for r in results if isinstance(r, Exception))
    success = CONCURRENT_USERS - errors

    logger.info(f"\n📊 Итоги стресс-теста:")
    logger.info(f"   ⏱ Время: {elapsed:.2f} сек")
    logger.info(f"   📈 Всего операций: ~{total_requests * 3} (чтение+запись+лог)")
    logger.info(f"   ✅ Успешно: {success}/{CONCURRENT_USERS} пользователей")
    logger.info(f"   ❌ Ошибок: {errors}")
    logger.info(f"   🚦 Пропускная способность: {total_requests / elapsed:.1f} запросов/сек на пользователя")

    # 5. Проверка целостности данных
    cursor = await db.conn.execute("SELECT COUNT(*) FROM generation_requests WHERE user LIKE '100%'")
    logged = (await cursor.fetchone())[0]
    logger.info(f"   📝 Записей в generation_requests: {logged} (ожидалось ~{total_requests})")

    # 6. Очистка
    await db.close()
    if Path(TEST_DB_PATH).exists():
        os.remove(TEST_DB_PATH)
        # Удаляем также WAL/SHM файлы, если остались
        for ext in ['-wal', '-shm']:
            p = Path(TEST_DB_PATH + ext)
            if p.exists():
                p.unlink()
        logger.info(f"🧹 Тестовая БД удалена")

    # 7. Финальный вердикт
    if errors == 0 and logged >= total_requests * 0.95:
        logger.info("🎉 СТРЕСС-ТЕСТ ПРОЙДЕН! БД готова к нагрузке.")
    else:
        logger.warning("⚠️ ТЕСТ ЗАВЕРШЁН С ПРЕДУПРЕЖДЕНИЯМИ. Проверь логи выше.")


if __name__ == "__main__":
    asyncio.run(run_stress_test())