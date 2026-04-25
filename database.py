import os
import logging
from peewee import (Model, SqliteDatabase, CharField,
                    IntegerField, DateTimeField, TextField, FloatField,OperationalError, BigIntegerField)
from datetime import datetime
import time
from db.user_preset import UserPreset
from db.user_quota import UserQuota

logger = logging.getLogger(__name__)
from config import DB_PATH

db = SqliteDatabase(
    DB_PATH,
    pragmas={
        'journal_mode': 'wal',       # 🔥 Crash-safe режим
        'synchronous': 'normal',     # Баланс скорости и безопасности
        'cache_size': -64 * 1024,    # 64 MB RAM-кэш
        'busy_timeout': 3000,        # Ждём 3 сек перед блокировкой
    }
)

class BaseModel(Model):
    class Meta:
        database = db

class UserSettings(BaseModel):
    """Настройки пользователя"""
    user_id = BigIntegerField(unique=True, index=True)
    username = CharField(max_length=100, null=True)

    # Настройки генерации
    model = TextField(null=True)  # путь к модели
    preset = CharField(max_length=50, null=True)  # ключ пресета

    requests_count = IntegerField(default=0)
    last_request_at = DateTimeField(null=True)

    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)

    class Meta:
        table_name = 'user_settings'
        indexes = (
            (('user_id',), True),  # unique
        )


class GenerationRequest(BaseModel):
    """История запросов — для аналитики и отладки"""
    user = CharField(max_length=20)  # user_id как строка
    prompt = TextField()
    model_used = TextField(null=True)
    preset_used = CharField(max_length=50, null=True)

    status = CharField(max_length=20, default='pending')  # pending, success, error
    error_message = TextField(null=True)

    queue_position = IntegerField(null=True)
    generation_time_sec = FloatField(null=True)

    created_at = DateTimeField(default=datetime.now)


    class Meta:
        table_name = 'generation_requests'
        indexes = (
            (('user', 'created_at'), False),
            (('status',), False),
        )

def init_db():
    """Создаёт таблицы если их нет"""
    db.connect(reuse_if_open=True)
    db.create_tables([
        UserSettings,
        GenerationRequest,
        UserPreset,
        UserQuota,
     ], safe=True)
    db.close()
    logger.info(f"🗄️ БД инициализирована: {DB_PATH}")

def close_db():
    """Закрывает соединение"""
    if not db.is_closed():
        db.close()
        logger.info("🔌 БД отключена")

from contextlib import contextmanager

@contextmanager
def db_session():
    """
    Безопасный контекст для работы с БД.
    • Автоматически открывает/закрывает соединение
    • Retry при 'database is locked' (до 3 попыток)
    • Идеально для долгой работы бота
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            db.connect(reuse_if_open=True)
            yield
            break
        except OperationalError as e:
            if "database is locked" in str(e).lower():
                wait = 0.5 * (attempt + 1)
                logger.warning(f"🔒 БД заблокирована, жду {wait}с (попытка {attempt+1})")
                time.sleep(wait)
            else:
                raise
        finally:
            if not db.is_closed():
                db.close()

init_db()