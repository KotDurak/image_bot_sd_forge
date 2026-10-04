# models/promo_codes.py
from typing import Optional, Dict, Any
import logging
from db.async_core import async_db  # 🔥 наш aiosqlite синглтон
from datetime import datetime, timedelta
logger = logging.getLogger(__name__)


async def create_promo_code(
        code: str,
        bonus_paid_credits: int = 0,
        bonus_free_limit: int = 0,
        max_uses: Optional[int] = None,
        created_by: Optional[int] = None
) -> bool:
    """
    Создает новый промокод.
    Возвращает True при успехе, False если код уже существует.
    """
    code = code.upper().strip()

    try:
        await async_db.conn.execute(
            """INSERT INTO promo_codes 
               (code, bonus_paid_credits, bonus_free_limit, max_uses, created_by) 
               VALUES (?, ?, ?, ?, ?)""",
            (code, bonus_paid_credits, bonus_free_limit, max_uses, created_by)
        )
        await async_db.conn.commit()
        logger.info(f"✅ Промокод '{code}' успешно создан")
        return True
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            logger.warning(f"⚠️ Промокод '{code}' уже существует")
            return False
        logger.error(f"❌ Ошибка при создании промокода '{code}': {e}")
        raise


async def get_promo_code(code: str) -> Optional[Dict[str, Any]]:
    """Возвращает данные промокода или None, если не найден."""
    code = code.upper().strip()
    cursor = await async_db.conn.execute(
        "SELECT * FROM promo_codes WHERE code = ?", (code,)
    )
    row = await cursor.fetchone()
    if row:
        # Получаем имена колонок из cursor.description
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))
    return None


async def has_user_used_promo(user_id: int, promo_code_id: int) -> bool:
    """Проверяет, активировал ли уже этот пользователь данный промокод."""
    cursor = await async_db.conn.execute(
        "SELECT 1 FROM user_promo_uses WHERE user_id = ? AND promo_code_id = ?",
        (user_id, promo_code_id)
    )
    row = await cursor.fetchone()
    return row is not None


async def activate_promo_code(user_id: int, code: str) -> Dict[str, Any]:
    """
    Активирует промокод для пользователя.
    Возвращает словарь с результатом: {'success': bool, 'message': str, 'data': dict|None}
    """
    code = code.upper().strip()
    # 1. Получаем промокод
    promo = await get_promo_code(code)

    if not promo:
        return {"success": False, "message": "❌ Промокод не найден."}

    if not promo["is_active"]:
        return {"success": False, "message": "❌ Этот промокод деактивирован."}

    # 2. Проверяем лимит использований
    if promo["max_uses"] is not None and promo["current_uses"] >= promo["max_uses"]:
        return {"success": False, "message": "❌ Лимит активаций этого промокода исчерпан."}

    # 🔥 ЗАЩИТА ОТ НАКРУТКИ: Реферальный код может активировать только новичок
    if promo["type"] == "referral":
        cursor = await async_db.conn.execute(
            "SELECT created_at FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        user_row = await cursor.fetchone()

        # user_row - это кортеж, например: ('2023-10-01 12:00:00',) или None
        if user_row and user_row[0]:
            created_at_str = str(user_row[0])

            try:
                # Парсим стандартный формат SQLite: YYYY-MM-DD HH:MM:SS
                created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
                now = datetime.now()

                # Если аккаунт создан более 48 часов назад — блокируем
                if (now - created_at).total_seconds() > 48 * 3600:
                    return {
                        "success": False,
                        "message": "⚠️ Реферальные коды можно активировать только в первые 48 часов после первого запуска бота."
                    }
            except ValueError:
                # Если формат даты нестандартный, просто пропускаем проверку, чтобы не ломать логику
                logger.warning(f"Не удалось распарсить дату created_at для юзера {user_id}: {created_at_str}")

    # 3. Проверяем, не использовал ли его уже этот юзер
    if await has_user_used_promo(user_id, promo["id"]):
        return {"success": False, "message": "❌ Вы уже активировали этот промокод ранее."}

    try:
        # 4. Выполняем все изменения в одной транзакции
        # 4.1. Увеличиваем счетчик использований промокода
        await async_db.conn.execute(
            "UPDATE promo_codes SET current_uses = current_uses + 1 WHERE id = ?",
            (promo["id"],)
        )

        # 4.2. Фиксируем факт использования пользователем
        await async_db.conn.execute(
            "INSERT INTO user_promo_uses (user_id, promo_code_id) VALUES (?, ?)",
            (user_id, promo["id"])
        )

        # 4.3. Прибавляем бонусы к существующим квотам
        cursor = await async_db.conn.execute(
            "SELECT id, paid_credits, free_limit FROM user_quota WHERE user_id = ?",
            (user_id,)
        )
        quota_row = await cursor.fetchone()

        if quota_row:
            # ✅ Запись есть — прибавляем к текущим значениям
            current_paid = quota_row[1] or 0
            current_free = quota_row[2] or 0

            await async_db.conn.execute(
                """UPDATE user_quota 
                   SET paid_credits = paid_credits + ?, 
                       free_limit = free_limit + ? 
                   WHERE user_id = ?""",
                (promo["bonus_paid_credits"], promo["bonus_free_limit"], user_id)
            )
            logger.info(
                f"📊 Обновлены квоты user_{user_id}: paid +{promo['bonus_paid_credits']}, free +{promo['bonus_free_limit']}")
        else:
            # ⚠️ Записи нет — создаем только с бонусом (стартовые 10 должны быть добавлены в /start)
            logger.warning(f"️ user_quota не найден для user_{user_id}, создаем с бонусом промокода")
            await async_db.conn.execute(
                """INSERT INTO user_quota (user_id, paid_credits, free_limit) 
                   VALUES (?, ?, ?)""",
                (user_id, promo["bonus_paid_credits"], promo["bonus_free_limit"])
            )

        await async_db.conn.commit()

        logger.info(f"✅ Юзер {user_id} успешно активировал промокод '{code}'")

        return {
            "success": True,
            "message": f"🎉 Промокод активирован!\n\nНачислено:\n💳 Paid credits: +{promo['bonus_paid_credits']}\n🎁 Free limit: +{promo['bonus_free_limit']}",
            "data": promo
        }

    except Exception as e:
        await async_db.conn.rollback()  # 🔥 Откат при любой ошибке, чтобы не было рассинхрона
        logger.error(f"❌ Ошибка при активации промокода '{code}' для юзера {user_id}: {e}")
        return {"success": False, "message": "⚠️ Произошла внутренняя ошибка при активации. Попробуйте позже."}


# models/promo_codes.py (дополнения)

async def get_or_create_user_referral_code(user_id: int) -> str:
    """
    Возвращает существующий реферальный код пользователя или создает новый.
    """
    code = f"REF{user_id}"

    # Проверяем, есть ли уже
    cursor = await async_db.conn.execute(
        "SELECT id FROM promo_codes WHERE code = ? AND type = 'referral'",
        (code,)
    )
    row = await cursor.fetchone()

    if row:
        return code

    # 🎁 НАСТРОЙКИ НАГРАД
    REWARD_FOR_CREATOR = 5  # Сколько получает тот, КТО ПОДЕЛИЛСЯ (paid_credits)
    REWARD_FOR_INVITED = 5  # Сколько получает тот, КТО ВВЕЛ КОД (free_limit)

    # Создаем новый реферальный код
    # 🔥 ДОБАВЛЕНО: created_by = user_id
    await async_db.conn.execute(
        """INSERT INTO promo_codes 
           (code, type, bonus_paid_credits, bonus_free_limit, 
            reward_paid_credits, reward_free_limit, is_active, max_uses, created_by) 
           VALUES (?, 'referral', 0, ?, ?, 0, 1, NULL, ?)""",
        (code, REWARD_FOR_INVITED, REWARD_FOR_CREATOR, user_id)
    )
    await async_db.conn.commit()
    logger.info(f"✅ Создан реферальный код {code} для user_{user_id}")
    return code


async def has_active_referral(user_id: int) -> bool:
    """Проверяет, активировал ли пользователь какой-либо реферальный код."""
    cursor = await async_db.conn.execute(
        """SELECT 1 FROM user_promo_uses upu
           JOIN promo_codes pc ON upu.promo_code_id = pc.id
           WHERE upu.user_id = ? AND pc.type = 'referral'""",
        (user_id,)
    )
    return (await cursor.fetchone()) is not None


async def reward_referral_creator(user_id: int) -> bool:
    """
    Вызывается после успешной генерации изображения.
    """
    cursor = await async_db.conn.execute(
        """SELECT upu.id, pc.created_by, pc.reward_paid_credits, pc.reward_free_limit
           FROM user_promo_uses upu
           JOIN promo_codes pc ON upu.promo_code_id = pc.id
           WHERE upu.user_id = ? AND pc.type = 'referral' AND upu.creator_rewarded = 0
           LIMIT 1""",
        (user_id,)
    )
    row = await cursor.fetchone()

    if not row:
        return False

    use_id, creator_id, reward_paid, reward_free = row

    # 🔥 ЗАЩИТА: если creator_id = None, пропускаем
    if creator_id is None:
        logger.warning(f"⚠️ Пропускаем начисление бонуса: created_by = NULL для use_id={use_id}")
        # Помечаем как начисленный, чтобы не пытаться снова
        await async_db.conn.execute(
            "UPDATE user_promo_uses SET creator_rewarded = 1 WHERE id = ?",
            (use_id,)
        )
        await async_db.conn.commit()
        return False

    try:
        # Начисляем бонус создателю
        cursor2 = await async_db.conn.execute(
            "SELECT id FROM user_quota WHERE user_id = ?", (creator_id,)
        )
        quota_exists = await cursor2.fetchone()

        if quota_exists:
            await async_db.conn.execute(
                """UPDATE user_quota 
                   SET paid_credits = paid_credits + ?, free_limit = free_limit + ?
                   WHERE user_id = ?""",
                (reward_paid, reward_free, creator_id)
            )
        else:
            await async_db.conn.execute(
                """INSERT INTO user_quota (user_id, paid_credits, free_limit) 
                   VALUES (?, ?, ?)""",
                (creator_id, reward_paid, reward_free)
            )

        # Помечаем, что бонус начислен
        await async_db.conn.execute(
            "UPDATE user_promo_uses SET creator_rewarded = 1 WHERE id = ?",
            (use_id,)
        )
        await async_db.conn.commit()

        logger.info(f"🎁 Реферальный бонус начислен создателю {creator_id} за приглашение {user_id}")
        return True

    except Exception as e:
        await async_db.conn.rollback()
        logger.error(f" Ошибка начисления реферального бонуса: {e}")
        return False