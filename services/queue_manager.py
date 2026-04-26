# services/queue_manager.py
"""
🔄 Асинхронная очередь генерации с умным батчингом по моделям.
Принцип: минимизировать переключения моделей в VRAM, максимизировать пропускную способность.
"""
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

# =============================================================================
# === КОНСТАНТЫ ==============================================================
# =============================================================================

QUEUE_POLL_INTERVAL = 0.1  # Секунд между проверками пустой очереди
MAX_BATCH_SIZE = 4  # Макс. запросов в одной пачке
MODEL_SWITCH_TIMEOUT = 45  # Таймаут переключения модели в Forge (сек)
GENERATION_TIMEOUT = 120  # Таймаут на саму генерацию (сек)
MAX_STATS_ENTRIES = 100  # Лимит уникальных моделей в статистике
STATS_PRUNE_COUNT = 10  # Сколько наименее популярных удалять при переполнении


# =============================================================================
# === МОДЕЛИ ДАННЫХ ==========================================================
# =============================================================================

@dataclass
class QueueItem:
    """Элемент очереди генерации"""
    user_id: int
    prompt: str
    payload: dict
    message: Message
    progress_msg: Message
    callback: Callable[[dict], Awaitable[bytes]]
    created_at: float = field(default_factory=lambda: asyncio.get_event_loop().time())
    usage_type: str = "free"
    preset_used: Optional[str] = None
    show_ads: bool = False

    @property
    def model_key(self) -> Optional[str]:
        """Извлекает ключ модели из payload (для группировки по модели в VRAM)"""
        override = self.payload.get("override_settings", {})
        return (
                override.get("sd_model_checkpoint")
                or self.payload.get("model_name")
        )


# =============================================================================
# === ОСНОВНОЙ КЛАСС ОЧЕРЕДИ =================================================
# =============================================================================

class GenerationQueue:
    """
    Асинхронная очередь с умной группировкой по моделям.

    Принцип работы:
    1. Запросы собираются в буфер на ~1-2 секунды
    2. Воркер берёт пачку запросов на ТЕКУЩУЮ загруженную модель
    3. Если таких нет — переключается на самую популярную в очереди
    4. Обрабатывает пачку, затем повторяет
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

        # 🧠 Состояние воркера
        self._current_model: Optional[str] = None
        self._stats: Dict[str, int] = defaultdict(int)
        self._shutdown_event = asyncio.Event()

    # ─────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Запускает воркер очереди"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(), name="queue_worker")
        logger.info("🚀 Очередь генерации запущена")

    async def stop(self) -> None:
        """Останавливает воркер (ждёт завершения текущей задачи)"""
        logger.info("🛑 Остановка очереди...")
        self._running = False
        self._shutdown_event.set()

        if self._worker_task and not self._worker_task.done():
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Воркер не успел завершиться, отменяем принудительно")
                self._worker_task.cancel()
            except asyncio.CancelledError:
                pass

        logger.info(f"✅ Очередь остановлена. Обработано запросов: {sum(self._stats.values())}")

    async def add_request(self, item: QueueItem) -> bool:
        """Добавляет запрос в очередь и обновляет статус пользователя"""
        position = self._queue.qsize() + 1
        await self._update_progress(item, position)
        await self._queue.put(item)

        if model := item.model_key:
            self._stats[model] += 1
            self._prune_stats_if_needed()

        logger.info(f"📥 user_{item.user_id}: добавлен в очередь (#{position}), модель: {model or 'default'}")
        return True

    # ─────────────────────────────────────────────────────────────
    # Основной цикл воркера
    # ─────────────────────────────────────────────────────────────

    async def _worker_loop(self) -> None:
        """Бесконечный цикл обработки очереди с умной группировкой"""
        logger.info("🔧 Воркер очереди запущен")

        while self._running:
            try:
                if self._queue.empty():
                    await asyncio.sleep(QUEUE_POLL_INTERVAL)
                    continue

                batch = await self._collect_batch()
                if not batch:
                    await asyncio.sleep(QUEUE_POLL_INTERVAL)
                    continue

                target_model = batch[0].model_key
                if target_model and target_model != self._current_model:
                    await self._switch_model_safe(target_model)
                    self._current_model = target_model

                for item in batch:
                    await self._process_item(item)

            except asyncio.CancelledError:
                logger.info("🔄 Воркер остановлен (CancelledError)")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в воркере: {e}", exc_info=True)
                await asyncio.sleep(2)

    # ─────────────────────────────────────────────────────────────
    # Логика формирования пачки (batching)
    # ─────────────────────────────────────────────────────────────

    async def _collect_batch(self) -> List[QueueItem]:
        """Собирает пачку запросов на одну модель. Асинхронная версия без гонок."""
        if self._queue.empty():
            return []

        try:
            first = await self._queue.get()
            batch = [first]
            target_model = first.model_key

            while not self._queue.empty() and len(batch) < MAX_BATCH_SIZE:
                peek = self._peek_queue()
                if peek and peek.model_key == target_model:
                    item = await self._queue.get()
                    batch.append(item)
                else:
                    break

            logger.debug(f"📦 Batch: {len(batch)} items, model={target_model or 'default'}")
            return batch

        except Exception as e:
            logger.error(f"❌ _collect_batch error: {e}")
            return []

    # ─────────────────────────────────────────────────────────────
    # Переключение модели (с защитой от зависаний)
    # ─────────────────────────────────────────────────────────────

    async def _switch_model_safe(self, model_checkpoint: str) -> None:
        """Переключает модель в Forge с таймаутом и проверкой."""
        logger.info(f"🔄 Переключение модели: {self._current_model} → {model_checkpoint}")

        try:
            await asyncio.wait_for(
                switch_forge_model(model_checkpoint),
                timeout=MODEL_SWITCH_TIMEOUT
            )
            logger.info(f"✅ Модель загружена: {model_checkpoint}")
        except asyncio.TimeoutError:
            logger.error(f"⏰ Таймаут переключения модели: {model_checkpoint}")
            raise RuntimeError(f"Не удалось загрузить модель за {MODEL_SWITCH_TIMEOUT}с")
        except Exception as e:
            logger.error(f"❌ Ошибка переключения модели: {e}", exc_info=True)
            raise

    # ─────────────────────────────────────────────────────────────
    # Обработка одного запроса
    # ─────────────────────────────────────────────────────────────

    async def _process_item(self, item: QueueItem) -> None:
        """Обрабатывает один элемент очереди: генерация + отправка + возврат при ошибке"""
        user_id = item.user_id
        start_time = time.perf_counter()

        # 🔥 Извлекаем метаданные ОДИН РАЗ
        model, preset = self._extract_model_and_preset(item)
        logger.info(f"🎨 Генерация для user_{user_id}: {item.prompt[:50]}...")

        try:
            # 1️⃣ Генерация с таймаутом (в потоке, чтобы не блокировать asyncio)
            image_bytes = await asyncio.wait_for(
                asyncio.to_thread(item.callback, item.payload),
                timeout=GENERATION_TIMEOUT
            )
            gen_time = time.perf_counter() - start_time

            if not image_bytes:
                raise ValueError("Пустой ответ от Forge API")

            logger.info(f"✅ user_{user_id}: сгенерировано {len(image_bytes)} байт")

            # 2️⃣ Отправка картинки
            await send_image_with_actions(
                message=item.message,
                image_bytes=image_bytes,
                caption=item.prompt[:100]
            )

            # 3️⃣ Логирование генерации (получаем ID для привязки рекламы)
            gen_id = None
            try:
                gen_id = await log_generation(
                    user_id=user_id, prompt=item.prompt, model=model,
                    preset=preset, status="success", gen_time=gen_time
                )
            except Exception as e:
                logger.error(f"❌ Не удалось записать лог генерации: {e}", exc_info=True)

            # 4️⃣ Реклама: ТОЛЬКО если есть флаг И успешно записался лог
            if item.show_ads and gen_id is not None:
                from services.ad_renderer import show_ad_after_generation
                asyncio.create_task(show_ad_after_generation(item.message, gen_id=gen_id))

            logger.info(f"user_{user_id}: задача выполнена")

        except asyncio.TimeoutError:
            logger.error(f"⏰ user_{user_id}: таймаут генерации ({GENERATION_TIMEOUT}с)")
            await self._handle_generation_error(item, "timeout", time.perf_counter() - start_time)

        except Exception as e:
            logger.error(f"❌ user_{user_id}: ошибка генерации: {e}", exc_info=True)
            await self._handle_generation_error(item, str(e)[:200], time.perf_counter() - start_time)

        finally:
            self._queue.task_done()

    async def _handle_generation_error(
            self,
            item: QueueItem,
            error: str,
            gen_time: float
    ) -> None:
        """Обрабатывает ошибку генерации: возврат кредита + лог + уведомление"""
        await self._refund_if_needed(item)

        try:
            await log_generation(
                user_id=item.user_id, prompt=item.prompt,
                status="failed", error=error, gen_time=gen_time
            )
        except Exception as log_err:
            logger.error(f"❌ Не удалось записать лог ошибки: {log_err}")

        await item.message.reply_text(
            "😿 Ошибка при генерации. Кредит возвращён. Попробуй позже или напиши /help"
            if error != "timeout" else
            "😿 Генерация заняла слишком много времени. Кредит возвращён. Попробуй упростить промпт."
        )

    # ─────────────────────────────────────────────────────────────
    # Вспомогательные методы
    # ─────────────────────────────────────────────────────────────

    async def _update_progress(self, item: QueueItem, position: int) -> None:
        """Обновляет сообщение о прогрессе у пользователя"""
        text = (
            f"⏳ Ты в очереди: #{position}\n🎨 Запрос: `{item.prompt[:50]}...`"
            if position > 1 else "🎨 Генерирую..."
        )
        try:
            await item.progress_msg.edit_text(text)
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.debug(f"⚠️ Не удалось обновить прогресс: {e}")

    async def _refund_if_needed(self, item: QueueItem) -> None:
        """Возвращает кредит, если он был списан (вызывается только при ошибке)"""
        from models.user_quota import is_unlimited_user, refund_credit

        if await is_unlimited_user(item.user_id):
            return

        await refund_credit(item.user_id, item.usage_type)
        logger.info(f"💸 Возврат кредита ({item.usage_type}) для user_{item.user_id}")

    def _extract_model_and_preset(self, item: QueueItem) -> tuple[Optional[str], Optional[str]]:
        """Извлекает модель и пресет из QueueItem для логирования."""
        override = item.payload.get("override_settings", {})
        model = override.get("sd_model_checkpoint") or item.payload.get("model_name")

        if model and " [" in model:
            model = model.split(" [")[0]

        preset = getattr(item, "preset_used", None)
        return model, preset

    def _prune_stats_if_needed(self) -> None:
        """Удаляет наименее популярные модели из статистики, если превышен лимит"""
        if len(self._stats) <= MAX_STATS_ENTRIES:
            return

        least_popular = sorted(self._stats.items(), key=lambda x: x[1])[:STATS_PRUNE_COUNT]
        for key, _ in least_popular:
            del self._stats[key]

    def _peek_queue(self) -> Optional[QueueItem]:
        """Безопасный пик в очередь (через приватный атрибут, но изолированно)"""
        try:
            # ⚠️ Доступ к _queue._queue — хрупкий, но необходимый для peek без извлечения
            # Если asyncio.Queue изменит реализацию, этот метод потребует обновления
            return self._queue._queue[0] if self._queue._queue else None
        except (IndexError, AttributeError):
            return None

    # ─────────────────────────────────────────────────────────────
    # Свойства и отладка
    # ─────────────────────────────────────────────────────────────

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def stats(self) -> Dict[str, int]:
        """Возвращает статистику: сколько запросов на каждую модель"""
        return dict(self._stats)

    async def get_queue_snapshot(self) -> List[Dict]:
        """Для отладки: возвращает список ожидающих запросов"""
        now = asyncio.get_event_loop().time()
        return [
            {
                "user_id": item.user_id,
                "model": item.model_key,
                "prompt": item.prompt[:30] + "...",
                "waiting_sec": now - item.created_at
            }
            for item in list(self._queue._queue)
        ]