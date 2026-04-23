from peewee import (Model, SqliteDatabase, CharField, AutoField,
                    IntegerField, DateTimeField, TextField, FloatField, OperationalError, BooleanField, BigIntegerField)
import os
from pathlib import Path

from db.user_preset import UserPreset

DB_PATH = os.path.join(
     Path(__file__).resolve().parent.parent.parent,
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

db.execute_sql('ALTER TABLE userpreset RENAME TO userpreset_old')

# 2. Создать новую по правильной модели
db.create_tables([UserPreset], safe=True)

# 3. Перенести данные (если структура совместима)
db.execute_sql('''
    INSERT INTO userpreset (user_id, preset_key, name, prompt_suffix, 
                           negative_suffix, width, height, steps,
                           is_safe_for_business, is_premium, created_at)
    SELECT user_id, preset_key, name, prompt_suffix, 
           negative_suffix, width, height, steps,
           is_safe_for_business, is_premium, created_at
    FROM userpreset_old
''')

# 4. Удалить старую таблицу
db.execute_sql('DROP TABLE userpreset_old')