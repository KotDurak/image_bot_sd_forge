import os
import sqlite3
import logging

logger = logging.getLogger(__name__)

def init_db_from_schema(db_path: str = "bot_data.db", schema_path: str = "schema.sql"):
    """Создаёт/проверяет БД из файла схемы. Безопасно для повторного запуска."""
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Файл схемы не найден: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        sql = f.read()

    conn = sqlite3.connect(db_path)
    try:
        # PRAGMAs лучше ставить отдельно от DDL
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        # Выполняем схему (executescript автоматически коммитит)
        conn.executescript(sql)
        logger.info(f"✅ БД успешно инициализирована/проверена: {db_path}")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "bot_data.db")
    print(db_path)
    init_db_from_schema(db_path)