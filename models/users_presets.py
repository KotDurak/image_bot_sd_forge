# models/users_presets.py
from typing import Optional, List, Dict, Any
import logging
from db.async_core import async_db  # 🔥 наш aiosqlite синглтон

logger = logging.getLogger(__name__)


async def add_user_preset(
        user_id: int,
        preset_key: str,
        name: str,
        prompt_suffix: str = '',
        negative_suffix: str = '',
        width: int = 512,
        height: int = 768,
        steps: int = 25,
        is_premium: bool = False,
        cfg_scale = 7.0,
        sampler = 'Euler',
        scheduler= 'automatic',
        prompt_prefix=""
) -> bool:
    """
    Добавляет кастомный пресет пользователя.
    Возвращает True при успехе, False если ключ уже занят.
    """
    preset_key = preset_key.lower().strip()

    try:
        await async_db.conn.execute(
            """INSERT INTO user_preset 
               (user_id, preset_key, name, prompt_suffix, negative_suffix, 
                width, height, steps,  is_premium, cfg_scale, sampler, scheduler,prompt_prefix) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, preset_key, name.strip(), prompt_suffix, negative_suffix,
             width, height, steps, is_premium, cfg_scale, sampler, scheduler,prompt_prefix)
        )
        await async_db.conn.commit()
        logger.info(f"✅ Пресет '{preset_key}' создан для user_{user_id}")
        return True
    except Exception as e:  # sqlite3.IntegrityError при дубликате
        if "UNIQUE constraint failed" in str(e):
            logger.warning(f"⚠️ Пресет '{preset_key}' уже существует для user_{user_id}")
            return False
        raise  # перекидываем другие ошибки выше


async def get_user_preset(user_id: int, preset_key: str) -> Optional[Dict[str, Any]]:
    """
    Возвращает настройки пресета как словарь, или None если не найден.
    """
    if not preset_key:
        return None

    preset_key = preset_key.lower().strip()

    cursor = await async_db.conn.execute(
        """SELECT preset_key, name, prompt_suffix, negative_suffix, 
                  width, height, steps, is_safe_for_business, is_premium,
                  cfg_scale,sampler,scheduler,prompt_prefix
           FROM user_preset 
           WHERE user_id = ? AND preset_key = ?""",
        (user_id, preset_key)
    )
    row = await cursor.fetchone()

    if not row:
        return None

    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


async def list_user_presets(user_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает список всех пресетов пользователя (для меню /presets).
    """
    cursor = await async_db.conn.execute(
        """SELECT preset_key, name, width, height, steps, 
                  is_safe_for_business, is_premium 
           FROM user_preset 
           WHERE user_id = ? 
           ORDER BY name""",
        (user_id,)
    )
    rows = await cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]

    return [dict(zip(columns, row)) for row in rows]


async def delete_user_preset(user_id: int, preset_key: str) -> bool:
    """
    Удаляет пресет. Возвращает True если удалён, False если не найден.
    """
    preset_key = preset_key.lower().strip()

    cursor = await async_db.conn.execute(
        "DELETE FROM user_preset WHERE user_id = ? AND preset_key = ?",
        (user_id, preset_key)
    )
    await async_db.conn.commit()

    if cursor.rowcount > 0:
        logger.info(f"🗑️ Пресет '{preset_key}' удалён для user_{user_id}")
        return True
    else:
        logger.warning(f"⚠️ '{preset_key}' не найден для удаления (user_{user_id})")
        return False


async def preset_exists(user_id: int, preset_key: str) -> bool:
    """
    Быстрая проверка: существует ли пресет с таким ключом у пользователя.
    """
    preset_key = preset_key.lower().strip()

    cursor = await async_db.conn.execute(
        "SELECT 1 FROM user_preset WHERE user_id = ? AND preset_key = ? LIMIT 1",
        (user_id, preset_key)
    )
    row = await cursor.fetchone()
    return row is not None