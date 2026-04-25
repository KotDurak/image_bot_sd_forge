import asyncio
from db.async_core import async_db


async def main():
    await async_db.init()

    # Простейший запрос
    async with async_db.conn.execute("SELECT 1 as test") as cursor:
        row = await cursor.fetchone()
        print(f"✅ fetchone работает: {row[0]}")  # должно быть 1

    await async_db.close()


asyncio.run(main())