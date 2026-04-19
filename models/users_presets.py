from typing import Optional, List, Dict, Any
import logging
from database import init_db, close_db, db_session
from db.user_preset import UserPreset
from peewee import DoesNotExist, IntegrityError

logger = logging.getLogger(__name__)
init_db()

def add_user_preset(
    user_id: int,
    preset_key: str,
    name: str,
    prompt_suffix: str = '',
    negative_suffix: str = '',
    width: int = 512,
    height: int = 768,
    steps: int = 25,
    is_safe_for_business: bool = True,
    is_premium: bool = False
) -> bool:
    """
        Добавляет кастомный пресет пользователя.
        Возвращает True при успехе, False если ключ уже занят.
    """
    with db_session():
        try:
            UserPreset.create(
                user_id=user_id,
                preset_key=preset_key.lower().strip(),  # нормализуем ключ
                name=name.strip(),
                prompt_suffix=prompt_suffix,
                negative_suffix=negative_suffix,
                width=width,
                height=height,
                steps=steps,
                is_safe_for_business=is_safe_for_business,
                is_premium=is_premium
            )
            logger.info(f" Пресет '{preset_key}' создан для user_{user_id}")
            return True
        except IntegrityError:
            logger.warning(f"Пресет '{preset_key}' уже существует для user_{user_id}")
            return False

def get_user_preset(user_id: int, preset_key: str) -> Optional[Dict[str, Any]]:
    """
    Возвращает настройки пресета как словарь, или None если не найден.
    """
    if not preset_key:
        return None
    with db_session():
        try:
            record = UserPreset.get(
                (UserPreset.user_id == user_id) &
                (UserPreset.preset_key == preset_key.lower())
            )
            return {
                "preset_key": record.preset_key,
                "name": record.name,
                "prompt_suffix": record.prompt_suffix,
                "negative_suffix": record.negative_suffix,
                "width": record.width,
                "height": record.height,
                "steps": record.steps,
                "is_safe_for_business": record.is_safe_for_business,
                "is_premium": record.is_premium,
            }
        except DoesNotExist:
            return None

def list_user_presets(user_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает список всех пресетов пользователя (для меню /presets).
    """
    with db_session():
        records = UserPreset.select().where(UserPreset.user_id == user_id).order_by(UserPreset.name)
        return [
            {
                "preset_key": r.preset_key,
                "name": r.name,
                "width": r.width,
                "height": r.height,
                "steps": r.steps,
                "is_safe_for_business": r.is_safe_for_business,
                "is_premium": r.is_premium,
            }
            for r in records
        ]

def delete_user_preset(user_id: int, preset_key: str) -> bool:
    """
    Удаляет пресет. Возвращает True если удалён, False если не найден.
    """
    with db_session():
        try:
            record = UserPreset.get(
                (UserPreset.user_id == user_id) &
                (UserPreset.preset_key == preset_key.lower())
            )
            record.delete_instance()
            logger.info(f"Пресет '{preset_key}' удалён для user_{user_id}")
            return True
        except DoesNotExist:
            logger.warning(f"'{preset_key}' не найден для удаления (user_{user_id})")
            return False

def preset_exists(user_id: int, preset_key: str) -> bool:
    """
    Быстрая проверка: существует ли пресет с таким ключом у пользователя.
    """
    with db_session():
        return UserPreset.select().where(
            (UserPreset.user_id == user_id) &
            (UserPreset.preset_key == preset_key.lower())
        ).exists()