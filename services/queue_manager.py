# services/queue_manager.py
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Dict, List
from collections import defaultdict
from models.generation_log import log_generation
import time
from utils.tg_helpers import send_image_with_actions

import httpx
from telegram import Message

from services.forge_api import  switch_forge_model

logger = logging.getLogger(__name__)


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
    preset_used: str | None = None

    @property
    def model_key(self) -> Optional[str]:
        """Извлекает ключ модели из payload (для группировки)"""
        return (
                self.payload.get("override_settings", {})
                .get("sd_model_checkpoint")
                or self.payload.get("model_name")
        )


class GenerationQueue:
    """
    Асинхронная очередь с умной группировкой по моделям.

    Принцип работы:
    1. Запросы собираются в буфер на ~1-2 секунды
    2. Воркер берёт пачку запросов на ТЕКУЩУЮ загруженную модель
    3. Если таких нет — переключается на самую популярную в очереди
    4. Обрабатывает пачку, затем повторяет
    """

    # ⏱ Настройки поведения
    MAX_BATCH_SIZE = 4  # Макс. запросов в одной пачке (чтобы не блокировать других)
    MODEL_SWITCH_TIMEOUT = 45  # Таймаут на переключение модели в Forge (сек)
    GENERATION_TIMEOUT = 120  # Таймаут на саму генерацию (сек)

    def __init__(self):
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

        # 🧠 Состояние воркера
        self._current_model: Optional[str] = None  # Какая модель сейчас в VRAM
        self._stats: Dict[str, int] = defaultdict(int)
        self._MAX_STATS_ENTRIES = 100  # Лимит уникальных моделей в статистике
        self._shutdown_event = asyncio.Event()

    # ─────────────────────────────────────────────────────────────
    # Публичный API
    # ─────────────────────────────────────────────────────────────

    async def start(self):
        """Запускает воркер очереди"""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop(), name="queue_worker")
        logger.info("🚀 Очередь генерации запущена")

    async def stop(self):
        """Останавливает воркер (ждёт завершения текущей задачи)"""
        logger.info("🛑 Остановка очереди...")
        self._running = False
        self._shutdown_event.set()

        if self._worker_task and not self._worker_task.done():
            # Даём 5 сек на завершение текущей генерации
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

        # Обновляем статус в Телеграме
        await self._update_progress(item, position)

        # Добавляем в очередь
        await self._queue.put(item)

        # Считаем статистику
        if model := item.model_key:
            self._stats[model] += 1

        if len(self._stats) > self._MAX_STATS_ENTRIES:
            # Удаляем 10 наименее популярных
            least_popular = sorted(self._stats.items(), key=lambda x: x[1])[:10]
            for key, _ in least_popular:
                del self._stats[key]

        logger.info(f"📥 user_{item.user_id}: добавлен в очередь (#{position}), модель: {model or 'default'}")
        return True

    # ─────────────────────────────────────────────────────────────
    # Основной цикл воркера
    # ─────────────────────────────────────────────────────────────

    async def _worker_loop(self):
        """Бесконечный цикл обработки очереди с умной группировкой"""
        logger.info("🔧 Воркер очереди запущен")

        while self._running:
            try:
                # 🔥 Если очередь пуста — засыпаем на 0.1с, чтобы не блокировать event loop!
                if self._queue.empty():
                    await asyncio.sleep(0.1)
                    continue

                # 1️⃣ Формируем пачку запросов
                batch = await self._collect_batch()
                if not batch:
                    await asyncio.sleep(0.1)
                    continue

                # 2️⃣ Переключаем модель, если нужно
                target_model = batch[0].model_key
                if target_model and target_model != self._current_model:
                    await self._switch_model_safe(target_model)
                    self._current_model = target_model

                # 3️⃣ Обрабатываем пачку последовательно
                for item in batch:
                    await self._process_item(item)

            except asyncio.CancelledError:
                logger.info("🔄 Воркер остановлен (CancelledError)")
                break
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в воркере: {e}", exc_info=True)
                await asyncio.sleep(2)  # Пауза перед повтором

    # ─────────────────────────────────────────────────────────────
    # Логика формирования пачки (batching)
    # ─────────────────────────────────────────────────────────────
    async def _collect_batch(self) -> List[QueueItem]:
        """
        Собирает пачку запросов на одну модель.
        Асинхронная версия без гонок условий.
        """
        # 🔥 Если очередь пуста — сразу выходим (не блокируем)
        if self._queue.empty():
            return []

        try:
            # Берём первый элемент
            first = await self._queue.get()
            batch = [first]
            target_model = first.model_key

            # 🔥 Быстро забираем ещё элементы на ту же модель (если есть)
            # Без сложных таймаутов — просто проверяем, что есть в очереди
            while (
                    not self._queue.empty() and
                    len(batch) < self.MAX_BATCH_SIZE
            ):
                # Смотрим следующий элемент, не извлекая
                peek = self._peek_queue()
                if peek and peek.model_key == target_model:
                    item = await self._queue.get()
                    batch.append(item)
                else:
                    break  # Другая модель — не трогаем, пусть ждёт своей очереди

            logger.debug(f"📦 Batch: {len(batch)} items, model={target_model or 'default'}")
            return batch

        except Exception as e:
            logger.error(f"❌ _collect_batch error: {e}")
            return []

    # ─────────────────────────────────────────────────────────────
    # Переключение модели (с защитой от зависаний)
    # ─────────────────────────────────────────────────────────────

    async def _switch_model_safe(self, model_checkpoint: str):
        """
        Переключает модель в Forge с таймаутом и проверкой.
        Вызывается только если target_model != self._current_model
        """
        logger.info(f"🔄 Переключение модели: {self._current_model} → {model_checkpoint}")

        try:
            # Отправляем команду переключения
            await asyncio.wait_for(
                switch_forge_model(model_checkpoint),
                timeout=self.MODEL_SWITCH_TIMEOUT
            )
            logger.info(f"✅ Модель загружена: {model_checkpoint}")

        except asyncio.TimeoutError:
            logger.error(f"⏰ Таймаут переключения модели: {model_checkpoint}")
            raise RuntimeError(f"Не удалось загрузить модель за {self.MODEL_SWITCH_TIMEOUT}с")
        except Exception as e:
            logger.error(f"❌ Ошибка переключения модели: {e}", exc_info=True)
            raise

    # ─────────────────────────────────────────────────────────────
    # Обработка одного запроса
    # ─────────────────────────────────────────────────────────────

    async def _process_item(self, item: QueueItem):
        """Обрабатывает один элемент очереди: генерация + отправка + возврат при ошибке"""
        user_id = item.user_id
        start_time = time.perf_counter()
        logger.info(f"🎨 Генерация для user_{user_id}: {item.prompt[:50]}...")
        model, preset = self._extract_model_and_preset(item)

        try:
            model, preset = self._extract_model_and_preset(item)
            # 1️⃣ Генерация с таймаутом
            image_bytes = await asyncio.wait_for(
                asyncio.to_thread(item.callback, item.payload),
                timeout=self.GENERATION_TIMEOUT
            )

            gen_time = time.perf_counter() - start_time

            if not image_bytes:
                raise ValueError("Пустой ответ от Forge API")

            logger.info(f"✅ user_{user_id}: сгенерировано {len(image_bytes)} байт")

            # Отправка с кнопками действий
            await send_image_with_actions(
                message=item.message,
                image_bytes=image_bytes,
                caption=item.prompt[:100]
            )

            try:
                await log_generation(
                    user_id=user_id, prompt=item.prompt, model=model,
                    preset=preset, status="success", gen_time=gen_time
                )
            except Exception as e:
                logger.error(f"❌ Не удалось записать лог генерации: {e}", exc_info=True)
            logger.info(f"user_{user_id}: задача выполнена")

        except asyncio.TimeoutError:
            logger.error(f"⏰ user_{user_id}: таймаут генерации ({self.GENERATION_TIMEOUT}с)")
            gen_time = time.perf_counter() - start_time
            # 🔥 Возврат при таймауте
            await self._refund_if_needed(item)
            try:
                await log_generation(
                    user_id=user_id, prompt=item.prompt, status="failed",
                    error="timeout", gen_time=gen_time
                )
            except Exception as log_err:
                logger.error(f"❌ Не удалось записать лог (таймаут): {log_err}")

            await item.message.reply_text(
                "😿 Генерация заняла слишком много времени. Кредит возвращён. Попробуй упростить промпт.")

        except Exception as e:
            logger.error(f"❌ user_{user_id}: ошибка генерации: {e}", exc_info=True)
            # 🔥 Возврат при любой другой ошибке
            await self._refund_if_needed(item)
            await item.message.reply_text("😿 Ошибка при генерации. Кредит возвращён. Попробуй позже или напиши /help")
            try:
                await log_generation(
                    user_id=user_id, prompt=item.prompt, status="failed",
                    error=str(e)[:200]
                )
            except Exception as log_err:
                logger.error(f"❌ Не удалось записать лог (таймаут): {log_err}")


        finally:
            # Всегда отмечаем задачу как выполненную (для task_done)
            self._queue.task_done()

    # ─────────────────────────────────────────────────────────────
    # Вспомогательные методы
    # ─────────────────────────────────────────────────────────────

    async def _update_progress(self, item: QueueItem, position: int):
        """Обновляет сообщение о прогрессе у пользователя"""
        text = (
            f"⏳ Ты в очереди: #{position}\n"
            f"🎨 Запрос: `{item.prompt[:50]}...`"
        ) if position > 1 else "🎨 Генерирую..."

        try:
            await item.progress_msg.edit_text(text)
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.debug(f"⚠️ Не удалось обновить прогресс: {e}")


    async def _refund_if_needed(self, item: QueueItem):
        """Возвращает кредит, если он был списан (вызывается только при ошибке)"""
        # Безлимитным ничего не возвращаем — они не тратили
        from models.user_quota import is_unlimited_user, refund_credit

        if await is_unlimited_user(item.user_id):
            return

        # Возвращаем кредит того типа, который был списан
        await refund_credit(item.user_id, item.usage_type)
        logger.info(f"💸 Возврат кредита ({item.usage_type}) для user_{item.user_id}")

    def _extract_model_and_preset(self, item: QueueItem) -> tuple[str | None, str | None]:
        """
        Извлекает модель и пресет из QueueItem для логирования.
        Возвращает (model_name, preset_name)
        """
        # 1. Модель: ищем в override_settings или на верхнем уровне
        model = (
                item.payload.get("override_settings", {}).get("sd_model_checkpoint")
                or item.payload.get("model_name")
        )
        # Очищаем от хэша для читаемости: "file.safetensors [abc123]" → "file.safetensors"
        if model and " [" in model:
            model = model.split(" [")[0]

        # 2. Пресет: передаём явно при создании QueueItem (см. ниже)
        preset = getattr(item, "preset_used", None)

        return model, preset

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
        items = []
        for item in list(self._queue._queue):
            items.append({
                "user_id": item.user_id,
                "model": item.model_key,
                "prompt": item.prompt[:30] + "...",
                "waiting_sec": asyncio.get_event_loop().time() - item.created_at
            })
        return items

    def _peek_queue(self) -> Optional[QueueItem]:
        """Безопасный пик в очередь (через приватный атрибут, но изолированно)"""
        try:
            return self._queue._queue[0] if self._queue._queue else None
        except (IndexError, AttributeError):
            return None