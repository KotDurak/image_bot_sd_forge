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
    Проверяет доступ к генерации.
    Возвращает (allowed: bool, status: str)
    """
    quota = await _get_or_create_quota(user_id)

    # 1. Забанен?
    if quota["is_banned"]:
        return False, "banned"

    # 2. Безлимит?
    if quota["is_unlimited"]:
        return True, "ok"

    # 3. Есть бесплатные?
    if quota["free_used"] < quota["free_limit"]:
        return True, "free"

    # 4. Есть платные?
    paid_available = quota.get("paid_credits", 0) - quota.get("paid_used", 0)
    if paid_available > 0:
        return True, "paid"

    # 5. Всё исчерпано
    return False, "no_credits"


async def increment_usage(user_id: int, usage_type: str = "free") -> bool:
    """
    Увеличивает счётчик использования.
    Возвращает True если счётчик обновлён, False если у пользователя безлимит.
    """
    quota = await _get_or_create_quota(user_id)

    # Безлимитным не считаем
    if quota["is_unlimited"]:
        return False

    if usage_type == "free":
        await async_db.conn.execute(
            "UPDATE user_quota SET free_used = free_used + 1 WHERE user_id = ?",
            (user_id,)
        )
    else:  # paid
        await async_db.conn.execute(
            "UPDATE user_quota SET paid_used = paid_used + 1 WHERE user_id = ?",
            (user_id,)
        )

    await async_db.conn.commit()
    logger.debug(f"📊 user_{user_id}: {usage_type}_used incremented")
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


async def add_paid_credits(user_id: int, user_credits: int) -> bool:
    """Начисляет платные кредиты пользователю"""
    await _get_or_create_quota(user_id)  # гарантируем существование

    await async_db.conn.execute(
        """UPDATE user_quota 
           SET paid_credits = paid_credits + ? 
           WHERE user_id = ?""",
        (user_credits, user_id)
    )
    await async_db.conn.commit()

    logger.info(f"💰 user_{user_id}: начислено {user_credits} платных кредитов")
    return True


async def get_quota_balance(user_id: int) -> tuple[int, int, int]:
    quota = await _get_or_create_quota(user_id)

    free_left = max(0, quota.get("free_limit", 0) - quota.get("free_used", 0))
    paid_left = max(0, quota.get("paid_credits", 0) - quota.get("paid_used", 0))
    return free_left, paid_left, free_left + paid_left

async def refund_credit(user_id: int, usage_type: str = "free") -> bool:
    """Возвращает 1 кредит. Безопасно (не уходит в минус)"""
    field = "free_used" if usage_type == "free" else "paid_used"
    await async_db.conn.execute(
        f"UPDATE user_quota SET {field} = MAX(0, {field} - 1) WHERE user_id = ?",
        (user_id,)
    )
    await async_db.conn.commit()
    logger.info(f"💸 Возврат 1 кредита ({usage_type}) для user_{user_id}")
    return True

async def is_unlimited_user(user_id: int) -> bool:
    """Проверяет, есть ли у пользователя безлимит"""
    quota = await _get_or_create_quota(user_id)
    return bool(quota.get("is_unlimited", False))

async def get_user_credits(user_id: int):
    cursor = await async_db.conn.execute(
        "SELECT paid_credits - paid_used FROM user_quota WHERE user_id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    return int(row[0])
