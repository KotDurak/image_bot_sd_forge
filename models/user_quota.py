from typing import Tuple, Optional
import logging
from db.async_core import async_db
import config

logger = logging.getLogger(__name__)


async def _get_or_create_quota(user_id: int) -> dict:
    """Внутренний хелпер: получить или создать запись квоты"""
    # Проверяем существование
    cursor = await async_db.conn.execute(
        "SELECT * FROM user_quota WHERE user_id = ?", (user_id,)
    )
    row = await cursor.fetchone()

    if row:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    # Создаём новую с дефолтами
    await async_db.conn.execute(
        """INSERT INTO user_quota 
           (user_id, is_banned, is_unlimited, free_used, free_limit) 
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, False, False, 0, config.DEFAULTS.get("free_limit", 10))
    )
    await async_db.conn.commit()

    return {
        "user_id": user_id,
        "is_banned": False,
        "is_unlimited": False,
        "free_used": 0,
        "free_limit": config.DEFAULTS.get("free_limit", 10)
    }


async def check_generation_limit(user_id: int) -> Tuple[bool, str]:
    """
    Проверяет, можно ли пользователю генерировать.
    Возвращает (allowed: bool, reason: str).
    """
    quota = await _get_or_create_quota(user_id)

    # 1. Забанен?
    if quota["is_banned"]:
        return False, "🚫 Доступ ограничен. Обратись к админу."

    # 2. Безлимит?
    if quota["is_unlimited"]:
        return True, "ok"

    # 3. Лимит исчерпан?
    if quota["free_used"] >= quota["free_limit"]:
        return False, f"⚠️ Лимит {quota['free_limit']} бесплатных генераций исчерпан."

    # 4. Всё ок
    return True, "ok"


async def increment_usage(user_id: int) -> bool:
    """
    Увеличивает счётчик использования.
    Возвращает True если счётчик обновлён, False если у пользователя безлимит.
    """
    quota = await _get_or_create_quota(user_id)

    # Безлимитным не считаем
    if quota["is_unlimited"]:
        return False

    await async_db.conn.execute(
        "UPDATE user_quota SET free_used = free_used + 1 WHERE user_id = ?",
        (user_id,)
    )
    await async_db.conn.commit()

    # Получаем актуальное значение для лога
    cursor = await async_db.conn.execute(
        "SELECT free_used, free_limit FROM user_quota WHERE user_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    if row:
        logger.debug(f"📊 user_{user_id}: free_used = {row[0]}/{row[1]}")

    return True


async def grant_unlimited(user_id: int, grant: bool = True) -> bool:
    """Выдать/забрать безлимит"""
    await _get_or_create_quota(user_id)  # гарантируем существование записи

    await async_db.conn.execute(
        "UPDATE user_quota SET is_unlimited = ? WHERE user_id = ?",
        (grant, user_id)
    )
    await async_db.conn.commit()

    status = "выдан" if grant else "забран"
    logger.info(f"♾️ Безлимит {status} для user_{user_id}")
    return True


async def ban_user(user_id: int, ban: bool = True) -> bool:
    """Забанить/разбанить пользователя"""
    await _get_or_create_quota(user_id)

    await async_db.conn.execute(
        "UPDATE user_quota SET is_banned = ? WHERE user_id = ?",
        (ban, user_id)
    )
    await async_db.conn.commit()

    status = "забанен" if ban else "разбанен"
    logger.info(f"🔒 user_{user_id} {status}")
    return True


async def reset_usage(user_id: int) -> bool:
    """Сбросить счётчик (для тестов или ручной компенсации)"""
    cursor = await async_db.conn.execute(
        "SELECT 1 FROM user_quota WHERE user_id = ?", (user_id,)
    )
    exists = await cursor.fetchone()

    if not exists:
        return False

    await async_db.conn.execute(
        "UPDATE user_quota SET free_used = 0 WHERE user_id = ?",
        (user_id,)
    )
    await async_db.conn.commit()

    logger.info(f"🔄 Счётчик сброшен для user_{user_id}")
    return True