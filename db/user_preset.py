import datetime

from peewee import (Model, SqliteDatabase, CharField, AutoField,
                    IntegerField, DateTimeField, TextField, FloatField, OperationalError, BooleanField, BigIntegerField)
import os

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'bot_data.db'
)

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

class UserPreset(BaseModel):
    """Кастомные пресеты пользователей"""
    id = AutoField(),
    user_id = BigIntegerField(index=True)

    # Идентификатор для команд и callback
    preset_key = CharField(max_length=50)

    # Отображаемое название
    name = CharField(max_length=50)

    # Настройки генерации
    prompt_suffix = TextField(default='')
    negative_suffix = TextField(default='')
    width = IntegerField(default=512)
    height = IntegerField(default=768)
    steps = IntegerField(default=25)

    # Флаги
    is_safe_for_business = BooleanField(default=True)
    is_premium = BooleanField(default=False)

    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        database = db
        indexes = (
            (('user_id', 'preset_key'), True),  # UNIQUE(user_id, preset_key)
        )