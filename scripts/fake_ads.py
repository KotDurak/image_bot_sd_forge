"""
Генератор фейковых показов для тестов.
Запуск: python -m scripts.fake_ads --ad_id 1 --count 50
"""

import asyncio
import sys
import random
from datetime import datetime, timedelta
import aiosqlite

# Добавляем корень проекта в path, чтобы импорты работали
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.async_core import async_db
import config


FAKE_PROMPTS = [
    "anime girl, white hair, detailed eyes, soft lighting",
    "cyberpunk city, neon lights, rain, futuristic",
    "fantasy landscape, castle, mountains, sunset",
    "cute cat, fluffy, anime style, big eyes",
    "warrior woman, armor, sword, epic background",
    "magical forest, glowing mushrooms, fairy lights",
    "space station, stars, sci-fi, detailed",
    "underwater scene, coral reef, tropical fish",
]


async def generate_fake_impressions(ad_id: int, count: int = 50):
    """Создаёт фейковые записи в ad_impressions_log"""
    # Берём случайные существующие генерации (чтобы JOIN работал)
    await async_db.init()
    cursor = await async_db.conn.execute(
        "SELECT id FROM generation_requests ORDER BY RANDOM() LIMIT ?",
        (count * 2,)  # Берём с запасом
    )
    gen_ids = [row[0] for row in await cursor.fetchall()]

    if not gen_ids:
        print("❌ Нет генераций в БД для привязки. Сначала сделай пару /gen")
        return

    for i in range(count):
        gen_id = random.choice(gen_ids)
        # Случайное время за последние 7 дней
        delta = timedelta(
            days=random.randint(0, 6),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        shown_at = (datetime.now() - delta).strftime("%Y-%m-%d %H:%M:%S")

        await async_db.conn.execute(
            "INSERT INTO ad_impressions_log (ad_id, generation_id, shown_at) VALUES (?, ?, ?)",
            (ad_id, gen_id, shown_at)
        )

    # Обновляем счётчик в кампании
    await async_db.conn.execute(
        "UPDATE ad_campaigns SET shown_count = shown_count + ?, remaining = MAX(0, remaining - ?) WHERE id = ?",
        (count, count, ad_id)
    )
    await async_db.conn.commit()
    print(f"✅ Сгенерировано {count} фейковых показов для кампании #{ad_id}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--ad_id", type=int, required=True, help="ID рекламной кампании")
    parser.add_argument("--count", type=int, default=50, help="Количество фейковых показов")
    args = parser.parse_args()

    asyncio.run(generate_fake_impressions(args.ad_id, args.count))