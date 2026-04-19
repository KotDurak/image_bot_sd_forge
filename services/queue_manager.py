import asyncio
import logging
from dataclasses import dataclass

import httpx
from telegram import Message
from typing import Optional, Callable, Awaitable
from models.user_state import log_generation_request, update_last_request_time, increment_requests_count, get_user_settings
import time

from services.forge_api import call_forge_api

logger = logging.getLogger(__name__)

@dataclass
class QueueItem:
    user_id: int
    prompt: str
    payload: dict
    message: Message
    progress_msg: Message
    callback: Callable[[dict], Awaitable[bytes]]


class GenerationQueue:
    """
    Асинхронная очередь для генерации изображений.
    Обрабатывает запросы последовательно, чтобы не перегрузить GPU.
    """

    def __init__(self):
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Очередь генерации запущена")

    async def stop(self):
        """Останавливает воркер"""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 Очередь генерации остановлена")

    async def add_request(self, item: QueueItem) -> bool:
        """Добавляет запрос в очередь"""
        position = self._queue.qsize() + 1

        if position > 1:
            await item.progress_msg.edit_text(
                f"⏳ Ты в очереди: #{position}\n"
                f"🎨 Запрос: `{item.prompt[:50]}...`\n"
            )
        else:
            try:
                await item.progress_msg.edit_text("🎨 Генерирую...")
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    logger.debug(f"Не удалось обновить статус: {e}")
        await self._queue.put(item)
        logger.info(f"📥 Запрос от user_{item.user_id} добавлен в очередь (позиция #{position})")
        return True

    async def _worker_loop(self):
        """Основной цикл воркера очереди"""
        logger.info("🔧 Воркер очереди запущен")

        while self._running:  #
            try:

                item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=5.0
                )

                logger.info(f"🎨 Обработка задачи от user_{item.user_id}")

                # 1. Генерация с таймаутом (защита от зависания Forge)
                try:
                    image_bytes = await asyncio.wait_for(
                        asyncio.to_thread(call_forge_api, item.payload),
                        timeout=120  # 2 минуты максимум
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError("Генерация превысила лимит 120 сек")

                if not image_bytes:
                    raise ValueError("Forge вернул пустой результат")

                logger.info(f"✅ Генерация завершена ({len(image_bytes)} байт). Отправляю...")

                # 2. Отправка фото
                await self._send_with_retry(
                    message=item.message,
                    image_bytes=image_bytes,
                    caption=item.prompt[:100],  # 👇 Используем prompt, т.к. caption нет в dataclass
                    max_attempts=3
                )

                logger.info(f"✨ Задача user_{item.user_id} выполнена")

            except asyncio.TimeoutError:
                # Это таймаут ожидания задачи из очереди (нормально при остановке)
                if not self._running:
                    break
                continue

            except Exception as e:
                # 👇 Самое важное: полный стектрейс в логи!
                logger.error(f"❌ Ошибка в воркере: {e}", exc_info=True)
                # Если есть message, пробуем уведомить пользователя
                if 'item' in locals() and hasattr(item, 'message'):
                    try:
                        await item.message.reply_text("😿 Ошибка генерации. Попробуй позже.")
                    except:
                        pass

            finally:
                # 👇 ИСПРАВЛЕНО: self._queue.task_done()
                try:
                    self._queue.task_done()
                except:
                    pass
                # Небольшая пауза
                await asyncio.sleep(0.5)

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    async def _send_with_retry(self, message, image_bytes, caption, max_attempts=3):
        """Отправка фото с повторами при сетевых ошибках"""
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                await message.reply_photo(
                    photo=image_bytes,
                    caption=caption,
                    parse_mode="Markdown",
                    # 👇 Явный таймаут для отправки (меньше дефолтного)
                    api_kwargs={"read_timeout": 30}
                )
                return  # Успех — выходим
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_error = e
                logger.warning(f"🔄 Попытка {attempt}/{max_attempts} не удалась: {e}")
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка: 2с, 4с, 8с
            except Exception as e:
                # Не сетевая ошибка — сразу пробрасываем дальше
                raise e

        # Если все попытки исчерпаны
        raise last_error