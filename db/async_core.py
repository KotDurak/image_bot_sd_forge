import os
import aiosqlite
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

class AsyncDB:
    def __init__(self, path: str):
        self.path = DB_PATH
        self._conn: aiosqlite.Connection | None = None

    async def init(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.path)
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA busy_timeout=5000;")  # +2 сек к твоему 3000
            await self._conn.execute("PRAGMA synchronous=NORMAL;")
            await self._conn.execute("PRAGMA cache_size=-32000;")   # 32
            logger.info(f"🔌 AsyncDB инициализирована: {self.path}")

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.info("🔌 AsyncDB отключена")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Call .init() first")
        return self._conn

# Синглтон
async_db = AsyncDB(os.path.join(os.path.dirname(__file__), "..", "bot_data.db"))