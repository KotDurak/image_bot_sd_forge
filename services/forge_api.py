import logging
import time
import base64
import requests
import config


logger = logging.getLogger(__name__)

def get_forge_auth():
    return (config.API_AUTH[0], config.API_AUTH[1]) if config.API_AUTH else None

def fetch_available_models():
    try:
        resp = requests.get(f"{config.FORGE_URL}/sdapi/v1/sd-models", auth=get_forge_auth(), timeout=30, proxies={'http': None, 'https': None})
        if resp.ok:
            return [(m.get('model_name', m['title']), m['title']) for m in resp.json()]
    except Exception as e:
        logger.error(f"❌ Не удалось получить модели: {e}")
    return [(n, f) for n, f in config.MODELS.items()]

def fetch_available_vae():
    try:
        resp = requests.get(f"{config.FORGE_URL}/sdapi/v1/sd-modules", auth=get_forge_auth(), timeout=30, proxies={'http': None, 'https': None})
        if resp.ok:
            result = [("🤖 Automatic (встроенный)", "Automatic")]
            for v in resp.json():
                name = v.get('model_name', v.get('filename', ''))
                label = name.replace('.safetensors', '')
                result.append((label, name))
            return result
    except Exception as e:
        logger.error(f"❌ Не удалось получить VAE: {e}")
    return [("🤖 Automatic", "Automatic")]

def call_forge_api(payload: dict) -> bytes | None:
    """🔥 Принимает готовый payload. Ничего не меняет. Отправляет как есть."""
    url = f"{config.FORGE_URL}/sdapi/v1/txt2img"
    start = time.time()
    try:
      #import json
      #logger.error(f"📤 FINAL PAYLOAD TO FORGE:\n{json.dumps(payload, indent=2, ensure_ascii=False)[:1500]}")
       #logger.info(f"🔗 POST {url} | prompt: {payload.get('prompt', '')[:50]}...")
        response = requests.post(
            url,
            json=payload,
            auth=get_forge_auth(),
            timeout=300,
            proxies={'http': None, 'https': None}
        )
        logger.info(f"⏱ Ответ за {time.time()-start:.2f}с | Статус: {response.status_code}")
        response.raise_for_status()
        res = response.json()
        if res.get("images"):
            return base64.b64decode(res["images"][0])
        logger.error("❌ В ответе нет изображений")
        return None
    except requests.exceptions.Timeout:
        logger.error("⏰ Таймаут: Forge не ответил за 300 сек")
        return None
    except Exception as e:
        logger.error(f"❌ API error: {e}")
        return None

def switch_forge_model(model_checkpoint: str) -> None:
    """Переключает модель. Таймаут контролируется вызывающим кодом (queue_manager)"""
    url = f"{config.FORGE_URL}/sdapi/v1/options"
    resp = requests.post(
        url,
        json={"sd_model_checkpoint": model_checkpoint},
        auth=get_forge_auth(),
        timeout=45,
        proxies={'http': None, 'https': None}
    )
    resp.raise_for_status()

def fetch_available_loras(user_id: int = None) -> list[dict]:
    """Получает список доступных LoRA. Возвращает [{'name': 'file.safetensors', 'alias': '...'}]."""
    try:
        resp = requests.get(f"{config.FORGE_URL}/sdapi/v1/loras", timeout=10)
        resp.raise_for_status()
        all_loras = resp.json()
        if not config.HIDDEN_LORAS or (user_id and user_id in config.ADMINS):
            return all_loras

        return [
            l for l in all_loras
            if l.get("name", "").lower() not in config.HIDDEN_LORAS
               and l.get("alias", "").lower() not in config.HIDDEN_LORAS
        ]

    except Exception as e:
        logger.error(f"fetch_available_loras error: {e}")
        return []