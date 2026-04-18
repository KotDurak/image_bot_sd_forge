import asyncio
import logging
from dataclasses import dataclass
from telegram import Message
from typing import Optional, Callable, Awaitable
from models.user_state import log_generation_request, update_last_request_time, increment_requests_count, get_user_settings
import time

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

    def __init__(self, max_concurrent: int = 1):
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._max_concurrent = max_concurrent
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
            await item.progress_msg.edit_text("Начинаю генерацию...")
        await self._queue.put(item)
        logger.info(f"📥 Запрос от user_{item.user_id} добавлен в очередь (позиция #{position})")
        return True

    async def _worker_loop(self):
        """Основной цикл воркера — обрабатывает запросы по одному"""
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue

            try:
                start_gen_time = time.time()
                logger.info(f"🎨 Обработка запроса от user_{item.user_id}: {item.prompt[:50]}...")

                # Обновляем статус
                await item.progress_msg.edit_text("⚙️ Генерация изображения...")

                # Выполняем тяжёлую операцию в потоке (чтобы не блокировать event loop)
                image_bytes = await asyncio.to_thread(item.callback, item.payload)
                gen_duration = time.time() - start_gen_time
                user_settings = get_user_settings(item.user_id)

                if image_bytes:
                    # ✅ Успех
                    update_last_request_time(item.user_id)
                    increment_requests_count(item.user_id)
                    log_generation_request(
                        user_id=item.user_id,
                        prompt=item.prompt,
                        model=user_settings.get('model'),
                        preset=user_settings.get('preset'),
                        status='success',
                        queue_pos=self.queue_size,
                        gen_time=gen_duration
                    )

                    await item.progress_msg.delete()
                    caption = f"✅ Готово!\n📝 `{item.prompt[:100]}{'...' if len(item.prompt) > 100 else ''}`"
                    await item.message.reply_photo(photo=image_bytes, caption=caption, parse_mode="Markdown")
                    logger.info(f"✅ Запрос user_{item.user_id} выполнен за {gen_duration:.1f}с")
                else:
                    await item.progress_msg.edit_text("❌ Ошибка генерации. Проверь логи Forge.")
                    # ❌ Ошибка генерации
                    log_generation_request(
                        user_id=item.user_id,
                        prompt=item.prompt,
                        status='error',
                        error='Forge API returned no image',
                        gen_time=gen_duration
                    )
                    logger.error(f"❌ Запрос user_{item.user_id} не выполнен")

            except asyncio.CancelledError:
                logger.warning(f"⚠️ Запрос user_{item.user_id} отменён")
                await item.progress_msg.edit_text("⚠️ Запрос отменён")
            except Exception as e:
                logger.error(f"❌ Ошибка в воркере: {e}", exc_info=True)
                log_generation_request(
                    user_id=item.user_id,
                    prompt=item.prompt,
                    status='error',
                    error=str(e),
                    gen_time=time.time() - start_gen_time if 'start_gen_time' in locals() else None
                )
                await item.progress_msg.edit_text(f"❌ Внутренняя ошибка: {type(e).__name__}")
            finally:
                self._queue.task_done()

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()