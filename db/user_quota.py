from peewee import (Model, SqliteDatabase, CharField,
                    IntegerField, DateTimeField, TextField, FloatField, OperationalError, BigIntegerField, BooleanField)
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


class UserQuota(BaseModel):
    """Лимиты и доступы пользователей"""
    user_id = BigIntegerField(unique=True, index=True)  # Telegram ID

    # Флаги доступа
    is_unlimited = BooleanField(default=False)  # VIP/админ: без лимита
    is_banned = BooleanField(default=False)  # Забанен (привет, Вася 🐱)

    # Счётчик бесплатных генераций
    free_used = IntegerField(default=0)  # Сколько уже использовал
    free_limit = IntegerField(default=5)  # Лимит (можно менять индивидуально)

    # Для будущего: сброс лимита по таймеру
    last_reset = DateTimeField(null=True)

    class Meta:
        database = db
        indexes = (
            (('user_id',), True),
        )