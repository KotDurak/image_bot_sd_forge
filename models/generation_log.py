import logging
from db.async_core import async_db

logger = logging.getLogger(__name__)

async def log_generation(
    user_id: int,
    prompt: str,
    model: str = None,
    preset: str = None,
    status: str = "success",
    error: str = None,
    gen_time: float = None,
    queue_pos: int = None
):
    """
        Запись в историю генераций.
        Адаптировано под твою схему: user (VARCHAR), queue_position (INT), etc.
        """
    cursor = await async_db.conn.execute("""
            INSERT INTO generation_requests 
            (user, prompt, model_used, preset_used, status, error_message, 
             queue_position, generation_time_sec, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
        str(user_id),  # user → VARCHAR
        prompt[:1000],  # prompt → обрезаем если слишком длинный
        model,  # model_used
        preset,  # preset_used
        status,  # status (pending|success|failed)
        error[:500] if error else None,  # error_message
        queue_pos,  # queue_position (обычно NULL, т.к. очередь уже ушла)
        round(gen_time, 2) if gen_time else None  # generation_time_sec
    ))
    await async_db.conn.commit()

    logger.debug(f"📝 Лог генерации: user_{user_id} | {status} | {gen_time or 0:.2f}с")
    return cursor.lastrowid


async def get_user_history(user_id: int, limit: int = 10) -> list[dict]:
    """Возвращает последние генерации пользователя"""
    cursor = await async_db.conn.execute("""
        SELECT id, prompt, model_used, preset_used, status, generation_time_sec, created_at
        FROM generation_requests
        WHERE user = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (str(user_id), limit))

    rows = await cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    return [dict(zip(columns, row)) for row in rows]