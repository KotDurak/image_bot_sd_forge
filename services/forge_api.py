import base64
import logging
import requests
from requests.auth import HTTPBasicAuth
import time
import config

logger = logging.getLogger(__name__)

def get_forge_auth():
    if config.API_AUTH and len(config.API_AUTH) == 2:
        return HTTPBasicAuth(config.API_AUTH[0], config.API_AUTH[1])
    return None

def fetch_available_models():
    """Получает список моделей из Forge API"""
    try:
        url = f"{config.FORGE_URL}/sdapi/v1/sd-models"
        resp = requests.get(url, auth=get_forge_auth(), timeout=30, proxies={'http': None, 'https': None})
        if resp.status_code == 200:
            models = resp.json()
            return [(m.get('model_name', m['title']), m['title']) for m in models]
    except Exception as e:
        logger.error(f"❌ Не удалось получить модели: {e}")
    # Фоллбэк на конфиг
    return [(name, filename) for name, filename in config.MODELS.items()]

def call_forge_api(payload: dict) -> bytes | None:
    """Отправляет запрос к Forge API, возвращает изображение в bytes"""
    url = f"{config.FORGE_URL}/sdapi/v1/txt2img"

    if 'model_name' in payload:
        payload['override_settings'] = {"sd_model_checkpoint": payload.pop("model_name")}
    start_time = time.time()
    try:
        if config.MODE == "DEV":
            logger.info(f"dev log: payload: {payload}")
        logger.info(f"🔗 POST {url} | prompt: {payload.get('prompt', '')[:50]}...")


        response = requests.post(
            url,
            json=payload,
            auth=get_forge_auth(),
            timeout=300,
            proxies={'http': None, 'https': None}
        )

        elapsed = time.time() - start_time
        logger.info(f"⏱ Ответ за {elapsed:.2f} сек | Статус: {response.status_code}")

        response.raise_for_status()
        result = response.json()

        if result.get("images"):
            return base64.b64decode(result["images"][0])
        logger.error("❌ В ответе нет изображений")
        return None
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут: Forge не ответил за 300 сек")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("🔌 Ошибка соединения: Forge недоступен")
        return None
    except Exception as e:
        logger.error(f"❌ API error: {e}")
        return None