import asyncio
import urllib.request
import urllib.parse
import json
import logging
import config

logger = logging.getLogger(__name__)


async def translate_prompt_free(prompt: str) -> str:
    """Бесплатный облачный перевод через MyMemory API. При любой ошибке возвращает оригинал."""
    if not getattr(config, "ENABLE_FREE_TRANSLATE", False):
        return prompt

    try:
        # Обрезаем промпт, чтобы не упереться в лимиты API
        max_len = int(getattr(config, "TRANSLATE_MAX_CHARS", 450))
        text = prompt[:max_len]

        url = "https://api.mymemory.translated.net/get"
        params = urllib.parse.urlencode({
            "q": text,
            "langpair": "ru|en",
            # Опционально: email для увеличения лимита (можно оставить пустым)
            "de": config.EMAIL
        })

        req = urllib.request.Request(f"{url}?{params}")
        req.add_header("User-Agent", "SD-TelegramBot/1.0")

        # Запускаем блокирующий запрос в отдельном потоке, чтобы не вешать асинхронный цикл
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, urllib.request.urlopen, req)

        data = json.loads(response.read().decode())
        translated = data.get("responseData", {}).get("translatedText")

        if translated and len(translated.strip()) > 0:
            logger.debug(f"Free translate OK: '{prompt[:30]}...' -> '{translated[:30]}...'")
            return translated

        # Если API вернул пустоту или ошибку в теле ответа
        return prompt

    except Exception as e:
        # 🐾 Главный принцип кота: нашкодил → быстро убери место преступления.
        # Лимит, блок, сеть, ошибка парсинга → просто игнорируем и отдаём как есть.
        logger.warning(f"Free translate failed silently: {e}")

        return prompt
