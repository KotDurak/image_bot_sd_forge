from typing import Tuple
import logging
from database import db_session
from db.user_quota import UserQuota
from peewee import DoesNotExist

logger = logging.getLogger(__name__)


def check_generation_limit(user_id: int) -> Tuple[bool, str]:
    """
    Проверяет, можно ли пользователю генерировать.
    Возвращает (allowed: bool, reason: str).
    """
    with db_session():
        quota, _ = UserQuota.get_or_create(user_id=user_id)
        print(quota, _)
        # 1. Забанен?
        if quota.is_banned:
            return False, "🚫 Доступ ограничен. Обратись к админу."

        # 2. Безлимит?
        if quota.is_unlimited:
            return True, "ok"

        # 3. Лимит исчерпан?
        if quota.free_used >= quota.free_limit:
            return False, f"⚠️ Лимит {quota.free_limit} бесплатных генераций исчерпан."

        # 4. Всё ок
        return True, "ok"


def increment_usage(user_id: int) -> bool:
    """
    Увеличивает счётчик использования.
    Возвращает True если счётчик обновлён, False если у пользователя безлимит.
    """
    with db_session():
        quota, _ = UserQuota.get_or_create(user_id=user_id)

        # Безлимитным не считаем
        if quota.is_unlimited:
            return False

        quota.free_used = UserQuota.free_used + 1
        quota.save()
        logger.debug(f"📊 user_{user_id}: free_used = {quota.free_used}/{quota.free_limit}")
        return True


def grant_unlimited(user_id: int, grant: bool = True) -> bool:
    """Выдать/забрать безлимит"""
    with db_session():
        quota, _ = UserQuota.get_or_create(user_id=user_id)
        quota.is_unlimited = grant
        quota.save()
        status = "выдан" if grant else "забран"
        logger.info(f"♾️ Безлимит {status} для user_{user_id}")
        return True


def ban_user(user_id: int, ban: bool = True) -> bool:
    """Забанить/разбанить пользователя"""
    with db_session():
        quota, _ = UserQuota.get_or_create(user_id=user_id)
        quota.is_banned = ban
        quota.save()
        status = "забанен" if ban else "разбанен"
        logger.info(f"🔒 user_{user_id} {status}")
        return True


def reset_usage(user_id: int) -> bool:
    """Сбросить счётчик (для тестов или ручной компенсации)"""
    with db_session():
        try:
            quota = UserQuota.get(UserQuota.user_id == user_id)
            quota.free_used = 0
            quota.save()
            logger.info(f"🔄 Счётчик сброшен для user_{user_id}")
            return True
        except DoesNotExist:
            return False