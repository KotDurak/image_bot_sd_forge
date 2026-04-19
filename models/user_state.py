from typing import Dict, Any
import logging
from database import UserSettings, init_db, close_db, db_session
from peewee import DoesNotExist

logger = logging.getLogger(__name__)
init_db()

def get_user_settings(user_id: int) -> Dict[str, Any]:
    with db_session():
        try:
            record = UserSettings.get(UserSettings.user_id == user_id)
            return {
                "model": record.model,
                "preset": record.preset,
                # можно добавить другие поля при необходимости
            }
        except DoesNotExist:
            UserSettings.create(user_id=user_id)
            return {"model": None, "preset": None}

def get_all_settings():
    with db_session():
        try:
            return UserSettings.select()
            return {
                "model": record.model,
                "preset": record.preset,
                # можно добавить другие поля при необходимости
            }
        except DoesNotExist:

            return []

def update_user_settings(user_id: int, username: str = None, **kwargs):
    with db_session():
        record, created = UserSettings.get_or_create(user_id=user_id)

        if username and not record.username:
            record.username = username

        for key, value in kwargs.items():
            if hasattr(record, key):
                setattr(record, key, value)
        record.save()
        logger.debug(f"💾 Сохранены настройки user_{user_id}: {kwargs}")

def get_last_request_time(user_id: int) -> float:
    with db_session():
        try:
            record = UserSettings.get(UserSettings.user_id == user_id)
            if record.last_request_at:
                return record.last_request_at.timestamp()
        except DoesNotExist:
            pass
        return 0


def update_last_request_time(user_id: int):
    with db_session():
        """Обновляет время последнего запроса"""
        from datetime import datetime
        record, _ = UserSettings.get_or_create(user_id=user_id)
        record.last_request_at = datetime.now()
        record.save()

def increment_requests_count(user_id: int):
    with db_session():
        """Увеличивает счётчик запросов"""
        record, _ = UserSettings.get_or_create(user_id=user_id)
        record.requests_count = UserSettings.requests_count + 1
        record.save()

from database import GenerationRequest
from datetime import datetime

def log_generation_request(
    user_id: int,
    prompt: str,
    model: str = None,
    preset: str = None,
    status: str = 'pending',
    error: str = None,
    queue_pos: int = None,
    gen_time: float = None
):
    with db_session():
        """Записывает факт генерации в историю"""
        GenerationRequest.create(
            user=str(user_id),
            prompt=prompt,
            model_used=model,
            preset_used=preset,
            status=status,
            error_message=error,
            queue_position=queue_pos,
            generation_time_sec=gen_time,
            created_at=datetime.now()
        )
        logger.info(f"📝 Записан запрос user_{user_id}: status={status}")


def get_user_settings_unsafe(user_id: int) -> Dict[str, Any]:
    import traceback
    logger.info(f"🔍 [DEBUG] Запрос настроек для user_{user_id}")

    try:
        # Временный обход db_session для диагностики
        record, created = UserSettings.get_or_create(user_id=int(user_id))

        logger.info(f"🔍 [DEBUG] Запись: id={record.id}, created={created}, preset_raw=[{record.preset!r}]")

        raw_preset = record.preset
        clean_preset = str(raw_preset).strip() if raw_preset is not None else None
        if clean_preset and clean_preset.lower() in ("none", "null", ""):
            clean_preset = None

        return {
            "model": getattr(record, "model", None),
            "preset": clean_preset,
            "last_request_at": getattr(record, "last_request_at", 0),
            "requests_count": getattr(record, "requests_count", 0)
        }
    except Exception as e:
        logger.error(f"❌ [DEBUG] get_user_settings упала для {user_id}: {e}")
        traceback.print_exc()  # 👈 Покажет точную строку и тип ошибки
        return {"model": None, "preset": None}