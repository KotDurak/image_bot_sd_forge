"""
Запуск: python -m db.migrator  или  python db/migrator.py
Применяет только новые .sql файлы из db/migrations/ в порядке версий.
Не зависит от жизненного цикла бота.
"""
import sqlite3
import sys
import logging
from pathlib import Path
from config import DB_PATH

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

def run_migrations(db_path: str = DB_PATH):
    if not MIGRATIONS_DIR.exists():
        logger.error(f"📁 Папка миграций не найдена: {MIGRATIONS_DIR}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")

    # Таблица учёта применённых миграций
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            version TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # Список уже применённых версий
    cursor = conn.execute("SELECT version FROM _migrations ORDER BY version")
    applied = {row[0] for row in cursor.fetchall()}

    # Сортируем файлы по префиксу версии (001_, 002_, ...)
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    pending = [f for f in files if f.stem.split("_")[0] not in applied]

    if not pending:
        logger.info("✅ Миграции: всё уже применено. Выход.")
        conn.close()
        return

    logger.info(f"🔄 Найдено {len(pending)} новых миграций.")

    for file_path in pending:
        version = file_path.stem.split("_")[0]
        logger.info(f"📄 Применяю: {file_path.name}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                sql = f.read()

            # ⚠️ SQLite: DDL (CREATE/ALTER) авто-коммитится. DML (INSERT/UPDATE) в executescript тоже.
            # Для безопасности пиши миграции идемпотентно (IF NOT EXISTS, ON CONFLICT)
            # или оборачивай DML в BEGIN; ... COMMIT;
            conn.executescript(sql)
            conn.execute("INSERT INTO _migrations (version) VALUES (?)", (version,))
            conn.commit()
            logger.info(f"✅ Миграция {version} применена успешно.")
        except Exception as e:
            logger.error(f"❌ Ошибка миграции {version}: {e}")
            conn.close()
            sys.exit(1)

    conn.close()
    logger.info("🎉 Все миграции применены. База готова.")

if __name__ == "__main__":
    run_migrations()