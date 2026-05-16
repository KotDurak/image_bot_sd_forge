# models/external_payments.py
import logging
from db.async_core import async_db

logger = logging.getLogger(__name__)


async def save_pending_payment(
    transaction_id: str, user_id: int, package_key: str, amount: int
) -> int:
    """
    Сохраняет платёж в статусе 'pending' и возвращает его DB id.
    """
    cursor = await async_db.conn.execute(
        """INSERT INTO external_payments 
           (transaction_id, user_id, package_key, amount, status)
           VALUES (?, ?, ?, ?, 'pending')""",
        (transaction_id, user_id, package_key, amount)
    )
    await async_db.conn.commit()
    payment_id = cursor.lastrowid  # 🔥 Получаем AUTOINCREMENT id
    logger.info(f"💳 pending: id={payment_id} | txn={transaction_id} | pkg={package_key}")
    return payment_id


async def get_payment_by_id(payment_id: int) -> dict | None:
    """Получает запись платежа по DB id"""
    cursor = await async_db.conn.execute(
        "SELECT * FROM external_payments WHERE id = ?", (payment_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def confirm_payment(payment_id: int, credits_granted: int) -> bool:
    """
    Меняет статус на 'confirmed' и записывает начисленные кредиты.
    Возвращает False, если платёж не найден или уже подтверждён.
    """
    cursor = await async_db.conn.execute(
        "SELECT status FROM external_payments WHERE id = ?", (payment_id,)
    )
    row = await cursor.fetchone()
    if not row or row[0] == 'confirmed':
        return False  # Уже обработан или не существует

    await async_db.conn.execute(
        "UPDATE external_payments SET status = 'confirmed', credits_granted = ? WHERE id = ?",
        (credits_granted, payment_id)
    )
    await async_db.conn.commit()
    logger.info(f"✅ confirmed: id={payment_id} | credits={credits_granted}")
    return True