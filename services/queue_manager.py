import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Dict, List

from telegram import Message
from models.generation_log import log_generation
from services.forge_api import switch_forge_model
from utils.tg_helpers import send_image_with_actions

logger = logging.getLogger(__name__)

QUEUE_POLL_INTERVAL = 0.1
MAX_BATCH_SIZE = 4
MODEL_SWITCH_TIMEOUT = 45
GENERATION_TIMEOUT = 120
MAX_STATS_ENTRIES = 100
STATS_PRUNE_COUNT = 10


@dataclass
class QueueItem:
    user_id: int
    prompt: str
    payload: dict  # 🔥 Immutable after creation in commands.py
    message: Message
    progress_msg: Message
    callback: Callable[[dict], Awaitable[bytes]]
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    usage_type: str = "free"
    preset_used: Optional[str] = None
    show_ads: bool = False

    @property
    def model_key(self) -> Optional[str]:
        """Извлекает ключ модели. Только чтение."""
        override = self.payload.get("override_settings", {})
        return override.get("sd_model_checkpoint")


class GenerationQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
        self._current_model: Optional[str] = None
        self._stats: Dict[str, int] = defaultdict(int)
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        if self._running: return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(), name="queue_worker")
        logger.info("🚀 Очередь генерации запущена")

    async def stop(self) -> None:
        logger.info("🛑 Остановка очереди...")
        self._running = False
        self._shutdown_event.set()
        if self._worker_task and not self._worker_task.done():
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
            except asyncio.CancelledError:
                pass
        logger.info(f"✅ Очередь остановлена. Обработано: {sum(self._stats.values())}")

    async def add_request(self, item: QueueItem) -> bool:
        position = self._queue.qsize() + 1
        await self._update_progress(item, position)
        await self._queue.put(item)
        if model := item.model_key:
            self._stats[model] += 1
            self._prune_stats_if_needed()
        logger.info(f"📥 user_{item.user_id}: добавлен (#{position}), модель: {model or 'default'}")
        return True

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                if self._queue.empty():
                    await asyncio.sleep(QUEUE_POLL_INTERVAL);
                    continue
                batch = await self._collect_batch()
                if not batch:
                    await asyncio.sleep(QUEUE_POLL_INTERVAL);
                    continue
                target_model = batch[0].model_key
                if target_model and target_model != self._current_model:
                    await self._switch_model_safe(target_model)
                    self._current_model = target_model
                for item in batch:
                    await self._process_item(item)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в воркере: {e}", exc_info=True)
                await asyncio.sleep(2)

    async def _collect_batch(self) -> List[QueueItem]:
        if self._queue.empty(): return []
        try:
            first = await self._queue.get()
            batch, target = [first], first.model_key
            while not self._queue.empty() and len(batch) < MAX_BATCH_SIZE:
                peek = self._peek_queue()
                if peek and peek.model_key == target:
                    batch.append(await self._queue.get())
                else:
                    break
            return batch
        except Exception as e:
            logger.error(f"❌ _collect_batch error: {e}");
            return []

    async def _switch_model_safe(self, model_checkpoint: str) -> None:
        """Переключает модель в Forge с таймаутом и проверкой."""
        logger.info(f"🔄 Переключение модели: {self._current_model} → {model_checkpoint}")

        try:
            # 🔥 FIX: оборачиваем синхронный вызов в поток
            await asyncio.wait_for(
                asyncio.to_thread(switch_forge_model, model_checkpoint),
                timeout=MODEL_SWITCH_TIMEOUT
            )
            logger.info(f"✅ Модель загружена: {model_checkpoint}")
        except asyncio.TimeoutError:
            logger.error(f"⏰ Таймаут переключения модели: {model_checkpoint}")
            raise RuntimeError(f"Не удалось загрузить модель за {MODEL_SWITCH_TIMEOUT}с")
        except Exception as e:
            logger.error(f"❌ Ошибка переключения модели: {e}", exc_info=True)
            raise

    async def _process_item(self, item: QueueItem) -> None:
        user_id, start_time = item.user_id, time.perf_counter()
        model, preset = self._extract_model_and_preset(item)
        logger.info(f"🎨 Генерация для user_{user_id}: {item.prompt[:50]}...")
        try:
            image_bytes = await asyncio.wait_for(
                asyncio.to_thread(item.callback, item.payload),  # 🔥 Передаём payload как есть
                timeout=GENERATION_TIMEOUT
            )
            if not image_bytes: raise ValueError("Пустой ответ от Forge API")
            await send_image_with_actions(item.message, image_bytes, item.prompt[:100])

            gen_id = None
            try:
                gen_id = await log_generation(user_id=user_id, prompt=item.prompt, model=model, preset=preset,
                                              status="success", gen_time=time.perf_counter() - start_time)
            except Exception as e:
                logger.error(f"❌ Ошибка логирования: {e}")

            if item.show_ads and gen_id:
                from services.ad_renderer import show_ad_after_generation
                asyncio.create_task(show_ad_after_generation(item.message, gen_id=gen_id))
        except asyncio.TimeoutError:
            logger.error(f"⏰ Таймаут генерации ({GENERATION_TIMEOUT}с)")
            await self._handle_generation_error(item, "timeout", time.perf_counter() - start_time)
        except Exception as e:
            logger.error(f"❌ Ошибка генерации: {e}", exc_info=True)
            await self._handle_generation_error(item, str(e)[:200], time.perf_counter() - start_time)
        finally:
            self._queue.task_done()

    async def _handle_generation_error(self, item: QueueItem, error: str, gen_time: float) -> None:
        await self._refund_if_needed(item)
        try:
            await log_generation(user_id=item.user_id, prompt=item.prompt, status="failed", error=error,
                                 gen_time=gen_time)
        except Exception as e:
            logger.error(f"❌ Ошибка логирования ошибки: {e}")
        await item.message.reply_text(
            "😿 Ошибка при генерации. Кредит возвращён. Попробуй позже или напиши /help" if error != "timeout" else "😿 Таймаут генерации. Кредит возвращён.")

    async def _update_progress(self, item: QueueItem, position: int) -> None:
        text = f"⏳ Ты в очереди: #{position}" if position > 1 else "🎨 Генерирую..."
        try:
            await item.progress_msg.edit_text(text)
        except Exception as e:
            if "message is not modified" not in str(e).lower(): logger.debug(f"⚠️ Прогресс: {e}")

    async def _refund_if_needed(self, item: QueueItem) -> None:
        from models.user_quota import is_unlimited_user, refund_credit
        if await is_unlimited_user(item.user_id): return
        await refund_credit(item.user_id, item.usage_type)

    def _extract_model_and_preset(self, item: QueueItem) -> tuple[Optional[str], Optional[str]]:
        override = item.payload.get("override_settings", {})
        model = override.get("sd_model_checkpoint")
        if model and " [" in model: model = model.split(" [")[0]
        return model, getattr(item, "preset_used", None)

    def _prune_stats_if_needed(self) -> None:
        if len(self._stats) <= MAX_STATS_ENTRIES: return
        for key, _ in sorted(self._stats.items(), key=lambda x: x[1])[:STATS_PRUNE_COUNT]: del self._stats[key]

    def _peek_queue(self) -> Optional[QueueItem]:
        try:
            return self._queue._queue[0] if self._queue._queue else None
        except (IndexError, AttributeError):
            return None

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()