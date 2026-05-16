import httpx
import logging
from typing import Optional
from config import PLATEGA_API_URL, PLATEGA_MERCHANT_ID, PLATEGA_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = PLATEGA_API_URL.rstrip("/")

async def create_payment(user_id: int, package_key: str, amount_rub: float, desc: str) -> Optional[dict]:
    headers = {
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_API_KEY,
        "Content-Type": "application/json"
    }

    # 🔥 description СТРОГО на корневом уровне
    # Формат для Telegram: TgId + UserId (можно через \n или пробел)
    description = f"TgId:{user_id} UserId:{user_id}"

    # 🔥 Структура ТОЧНО как в примере Пушка:
    payload = {
        "paymentDetails": {
            "amount": float(amount_rub),  # Platega принимает и int, и float
            "currency": "RUB"
            # ❌ description НЕ сюда!
        },
        "description": description,        # ✅ Вот сюда — на корневой уровень
        "return": "https://t.me/ТВОЙБОТ",  # ✅ Поле называется "return", не "returnUrl"
        "failedUrl": "https://t.me/ТВОЙБОТ",
        "payload": f"pkg:{package_key}:uid:{user_id}"
    }

    # 🐾 Дебаг-лог, чтобы видеть, что отправляем (в продакшене можно убрать или сделать level=DEBUG)
    logger.debug(f"Platega request: {payload}")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.post(
                f"{BASE_URL}/v2/transaction/process",
                json=payload,
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            logger.info(f"Platega response: {data}")

            return {
                "transaction_id": data.get("transactionId"),
                "payment_url": data.get("url"),
                "status": data.get("status"),
                "expires_in": data.get("expiresIn")
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"📡 HTTP {e.response.status_code}: {e.response.text}")
        raise
    except httpx.RequestError as e:
        logger.error(f"🌐 Сетевая ошибка: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        raise


async def check_payment_status(transaction_id: str) -> str:
    """
    Проверяет статус транзакции через GET /v2/transaction/{id}
    Возвращает: 'pending', 'confirmed', 'canceled', 'chargebacked', 'unknown'
    """
    headers = {
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{BASE_URL}/transaction/{transaction_id}",
                headers=headers
            )
            resp.raise_for_status()
            data = resp.json()

            # Platega возвращает статус в верхнем регистре: PENDING, CONFIRMED...
            raw_status = data.get("status", "UNKNOWN").upper()

            # Нормализуем для удобства
            status_map = {
                "PENDING": "pending",
                "CANCELED": "canceled",
                "CONFIRMED": "confirmed",  # ✅ Успешная оплата
                "CHARGEBACKED": "chargebacked"
            }
            return status_map.get(raw_status, "unknown")

    except httpx.HTTPStatusError as e:
        logger.warning(f"⚠️ Статус код {e.response.status_code} при проверке {transaction_id}")
        return "unknown"
    except Exception as e:
        logger.error(f"❌ Ошибка проверки статуса: {e}")
        return "unknown"