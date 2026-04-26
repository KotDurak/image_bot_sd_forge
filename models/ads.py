import logging
from db.async_core import async_db
import hashlib

logger = logging.getLogger(__name__)


async def fetch_pending_ad() -> dict | None:
    """Берёт случайную активную рекламу БЕЗ списания"""
    cursor = await async_db.conn.execute(
        "SELECT id, ad_type, content, target_link, btn_text, remaining "
        "FROM ad_campaigns WHERE is_active = 1 AND remaining > 0 "
        "ORDER BY RANDOM() LIMIT 1"
    )
    row = await cursor.fetchone()
    if not row:
        return None

    ad_id, ad_type, content, target_link, btn_text, remaining = row
    return {
        "id": ad_id, "ad_type": ad_type, "content": content,
        "target_link": target_link, "btn_text": btn_text
    }


async def confirm_ad_delivery(ad_id: int, gen_id: int) -> bool:
    """
    Подтверждает показ:
    1. Уменьшает remaining, увеличивает shown_count
    2. Пишет связь реклама↔генерация (без дублей!)
    3. Авто-деактивирует кампанию при remaining=0
    """
    # 1. Списываем показ
    await async_db.conn.execute(
        "UPDATE ad_campaigns SET remaining = remaining - 1, shown_count = shown_count + 1 "
        "WHERE id = ? AND remaining > 0",
        (ad_id,)
    )

    # 2. Логируем показ (только ad_id + gen_id, остальное берём через JOIN)
    await async_db.conn.execute(
        "INSERT INTO ad_impressions_log (ad_id, generation_id) VALUES (?, ?)",
        (ad_id, gen_id)
    )

    # 3. Авто-деактивация при нуле
    await async_db.conn.execute(
        "UPDATE ad_campaigns SET is_active = 0 WHERE id = ? AND remaining <= 0",
        (ad_id,)
    )

    await async_db.conn.commit()
    logger.info(f"✅ Реклама #{ad_id}: показана в генерации #{gen_id}")
    return True


async def get_campaign_report(ad_id: int, page: int = 1, per_page: int = 15) -> dict | None:
    """Пагинированный отчёт с JOIN к generation_requests"""
    # 1. Инфо о кампании
    cursor = await async_db.conn.execute(
        "SELECT id, title, ad_type, remaining, shown_count, is_active, created_at "
        "FROM ad_campaigns WHERE id = ?", (ad_id,)
    )
    row = await cursor.fetchone()
    if not row: return None

    cols = [d[0] for d in cursor.description]
    campaign = dict(zip(cols, row))

    # 2. Общее число показов
    cursor = await async_db.conn.execute(
        "SELECT COUNT(*) FROM ad_impressions_log WHERE ad_id = ?", (ad_id,)
    )
    total = (await cursor.fetchone())[0]

    # 3. Детализация с JOIN (берём только нужное, без дублей)
    offset = (page - 1) * per_page
    cursor = await async_db.conn.execute("""
        SELECT imp.shown_at, req.user, req.prompt, req.status
        FROM ad_impressions_log imp
        JOIN generation_requests req ON imp.generation_id = req.id
        WHERE imp.ad_id = ?
        ORDER BY imp.shown_at DESC
        LIMIT ? OFFSET ?
    """, (ad_id, per_page, offset))

    rows = await cursor.fetchall()
    impressions = [
        {"time": r[0], "user_id": r[1], "prompt": r[2], "status": r[3]}
        for r in rows
    ]

    return {
        "campaign": campaign,
        "total": total,
        "pages": max(1, (total + per_page - 1) // per_page),
        "current_page": page,
        "per_page": per_page,
        "impressions": impressions
    }


async def get_all_campaign_impressions(ad_id: int, anonymize: bool = True, salt: str = "") -> list[dict]:
    """Возвращает ВСЕ показы для CSV-экспорта (без пагинации)"""
    cursor = await async_db.conn.execute("""
        SELECT imp.shown_at, req.user, req.prompt
        FROM ad_impressions_log imp
        JOIN generation_requests req ON imp.generation_id = req.id
        WHERE imp.ad_id = ?
        ORDER BY imp.shown_at DESC
    """, (ad_id,))
    rows = await cursor.fetchall()
    result = []
    for r in rows:
        user_raw = str(r[1])
        if anonymize:
            if salt:
                # Хеш: воспроизводимо, но необратимо
                user_display = hashlib.sha256(f"{salt}_{user_raw}".encode()).hexdigest()[:12]
            else:
                # Маска: user_***58
                user_display = f"user_***{user_raw[-2:]}" if len(user_raw) >= 2 else "user_***"
        else:
            user_display = user_raw

        prompt = r[2] or ""
        result.append({"time": r[0], "user_id": user_display, "prompt": prompt})

    return result
    '''
    return [
        {"time": r[0], "user_id": str(r[1]), "prompt": r[2] or ""}
        for r in rows
    ] '''