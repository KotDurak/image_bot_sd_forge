# services/forge_options.py
"""
🔄 Кеширование доступных сэмплеров и шедулеров из Forge API.
При старте бота — один запрос, дальше — работа из памяти.
Если Forge недоступен — используем безопасные дефолты.
"""
import asyncio
import logging
import httpx
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 🔙 Фоллбэки на случай, если Forge не отвечает
DEFAULT_SAMPLERS = ["Euler", "Euler a", "DPM++ 2M", "DPM++ SDE", "UniPC", "DDIM"]
DEFAULT_SCHEDULERS = ["automatic", "normal", "karras", "exponential", "sgm_uniform", "simple"]


class ForgeOptionsCache:
    _samplers: Optional[List[str]] = None
    _schedulers: Optional[List[str]] = None
    _initialized = False
    _forge_url: str = ""

    @classmethod
    def init(cls, forge_url: str) -> None:
        cls._forge_url = forge_url.rstrip("/")
        cls._initialized = True

    @classmethod
    async def _fetch_from_api(cls, endpoint: str) -> Optional[List[str]]:
        """Делает запрос к Forge API и возвращает список name (в оригинальном регистре!)"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{cls._forge_url}/sdapi/v1/{endpoint}")
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):

                    return [item["name"] for item in data if "name" in item]
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить {endpoint} из Forge: {e}")
        return None

    @classmethod
    async def refresh(cls) -> None:
        """Принудительно обновляет кеш из API (для админа)"""
        if not cls._initialized:
            return
        samplers = await cls._fetch_from_api("samplers")
        schedulers = await cls._fetch_from_api("schedulers")

        if samplers:
            cls._samplers = samplers
            logger.info(f"✅ Загружено {len(samplers)} сэмплеров из Forge")
        if schedulers:
            cls._schedulers = schedulers
            logger.info(f"✅ Загружено {len(schedulers)} шедулеров из Forge")

    @classmethod
    async def ensure_loaded(cls) -> None:
        """Ленивая загрузка: если кеш пуст — пробуем загрузить"""
        if cls._samplers is None or cls._schedulers is None:
            await cls.refresh()
            # Если всё ещё пусто — ставим дефолты
            if cls._samplers is None:
                cls._samplers = DEFAULT_SAMPLERS
                logger.info("🔙 Используем дефолтные сэмплеры")
            if cls._schedulers is None:
                cls._schedulers = DEFAULT_SCHEDULERS
                logger.info("🔙 Используем дефолтные шедулеры")

    @classmethod
    def is_valid_sampler(cls, name: str) -> bool:
        #  FIX: сравниваем case-insensitive, но храним оригинал
        return any(name.lower() == s.lower() for s in (cls._samplers or DEFAULT_SAMPLERS))

    @classmethod
    def is_valid_scheduler(cls, name: str) -> bool:
        return any(name.lower() == s.lower() for s in (cls._schedulers or DEFAULT_SCHEDULERS))

    @classmethod
    def get_samplers(cls) -> List[str]:
        return cls._samplers or DEFAULT_SAMPLERS

    @classmethod
    def get_schedulers(cls) -> List[str]:
        return cls._schedulers or DEFAULT_SCHEDULERS