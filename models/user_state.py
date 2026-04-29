from datetime import datetime
from db.async_core import async_db
import logging

logger = logging.getLogger(__name__)

async def get_user_settings(user_id: int) -> dict:
    """Возвращает настройки пользователя"""
    # 1. Гарантируем существование записи (INSERT OR IGNORE безопасен и быстр)
    await async_db.conn.execute(
        """INSERT OR IGNORE INTO user_settings 
           (user_id, requests_count, created_at, updated_at) 
           VALUES (?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (user_id,)
    )
    await async_db.conn.commit()

    # 2. Читаем настройки
    cursor = await async_db.conn.execute(
        "SELECT model, preset, requests_count, vae, lora_string FROM user_settings WHERE user_id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()

    if not row:
        return {"model": None, "preset": None, "requests_count": 0, "vae": None, "lora_string": None}

    return {
        "model": row[0],
        "preset": row[1],
        "requests_count": row[2],
        "vae": row[3],  # Вернёт None, "Automatic" или "sdxl_vae.safetensors",
        "lora_string": row[4],
    }


async def update_user_settings(user_id: int, username: str = None, **kwargs):
    """Обновить настройки пользователя. Поддерживает динамическое обновление любых полей."""
    # Гарантируем наличие записи
    await async_db.conn.execute(
        """INSERT OR IGNORE INTO user_settings 
           (user_id, requests_count, created_at, updated_at) 
           VALUES (?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
        (user_id,)
    )
    await async_db.conn.commit()

    valid_fields = {'username', 'model', 'preset', 'requests_count', 'vae', 'last_request_at', 'lora_string'}
    updates = []
    params = []

    if username is not None:
        updates.append("username = ?")
        params.append(username)

    for key, value in kwargs.items():
        if key in valid_fields:
            updates.append(f"{key} = ?")
            params.append(value)

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(user_id)  # Последний параметр для WHERE

        query = f"""
            UPDATE user_settings 
            SET {', '.join(updates)}
            WHERE user_id = ?
        """
        await async_db.conn.execute(query, tuple(params))
        await async_db.conn.commit()
        logger.debug(f"💾 [async] Обновлено user_{user_id}: { {k: kwargs[k] for k in valid_fields & kwargs.keys()} }")