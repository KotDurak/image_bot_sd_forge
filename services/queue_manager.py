# services/queue_manager.py
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Dict, List
from collections import defaultdict

import httpx
from telegram import Message

from services.forge_api import call_forge_api, fetch_available_models, switch_forge_model

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
    created_at: float = field(default_factory=asyncio.get_event_loop().time)

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
    BATCH_TIMEOUT = 2  # Максимальное время ожидания формирования пачки (сек)
    MAX_BATCH_SIZE = 4  # Макс. запросов в одной пачке (чтобы не блокировать других)
    MODEL_SWITCH_TIMEOUT = 45  # Таймаут на переключение модели в Forge (сек)
    GENERATION_TIMEOUT = 120  # Таймаут на саму генерацию (сек)

    def __init__(self):
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False

        # 🧠 Состояние воркера
        self._current_model: Optional[str] = None  # Какая модель сейчас в VRAM
        self._stats: Dict[str, int] = defaultdict(int)  # Простая метрика: запросов на модель

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
                # 1️⃣ Формируем пачку запросов
                batch = await self._collect_batch()
                if not batch:
                    continue  # Очередь пуста, ждём дальше

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
                await asyncio.sleep(2)  # Небольшая пауза перед перезапуском цикла

    # ─────────────────────────────────────────────────────────────
    # Логика формирования пачки (batching)
    # ─────────────────────────────────────────────────────────────

    async def _collect_batch(self) -> List[QueueItem]:
        """
        Собирает пачку запросов на одну модель.

        Алгоритм:
        1. Берём первый элемент из очереди
        2. Ждём BATCH_TIMEOUT, собирая элементы на ту же модель
        3. Возвращаем пачку (макс. MAX_BATCH_SIZE элементов)
        """
        try:
            # Ждём первый элемент (с таймаутом, чтобы не висеть вечно)
            first = await asyncio.wait_for(self._queue.get(), timeout=2.0)
        except asyncio.TimeoutError:
            return []  # Очередь пуста

        batch = [first]
        target_model = first.model_key
        start_time = asyncio.get_event_loop().time()

        # Собираем остальные элементы той же модели
        while (
                len(batch) < self.MAX_BATCH_SIZE and
                asyncio.get_event_loop().time() - start_time < self.BATCH_TIMEOUT and
                not self._queue.empty()
        ):
            # Смотрим следующий элемент, не извлекая
            peek = self._queue._queue[0] if self._queue._queue else None
            if peek and peek.model_key == target_model:
                item = await self._queue.get()
                batch.append(item)
            else:
                break  # Следующий элемент на другой модели — не берём

        logger.debug(f"📦 Сформирована пачка: {len(batch)} запрос(ов), модель: {target_model or 'default'}")
        return batch

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
        """Обрабатывает один элемент очереди: генерация + отправка"""
        user_id = item.user_id
        logger.info(f"🎨 Генерация для user_{user_id}: {item.prompt[:50]}...")

        try:
            # 1️⃣ Генерация с таймаутом
            image_bytes = await asyncio.wait_for(
                asyncio.to_thread(item.callback, item.payload),
                timeout=self.GENERATION_TIMEOUT
            )

            if not image_bytes:
                raise ValueError("Пустой ответ от Forge API")

            logger.info(f"✅ user_{user_id}: сгенерировано {len(image_bytes)} байт")

            # 2️⃣ Отправка с повторами
            await self._send_with_retry(
                message=item.message,
                image_bytes=image_bytes,
                caption=item.prompt[:100]
            )

            logger.info(f"✨ user_{user_id}: задача выполнена")

        except asyncio.TimeoutError:
            logger.error(f"⏰ user_{user_id}: таймаут генерации ({self.GENERATION_TIMEOUT}с)")
            await item.message.reply_text("😿 Генерация заняла слишком много времени. Попробуй упростить промпт.")
        except Exception as e:
            logger.error(f"❌ user_{user_id}: ошибка генерации: {e}", exc_info=True)
            await item.message.reply_text("😿 Ошибка при генерации. Попробуй позже или напиши /help")
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

    async def _send_with_retry(
            self,
            message: Message,
            image_bytes: bytes,
            caption: str,
            max_attempts: int = 3
    ):
        """Отправка фото с экспоненциальной задержкой при сетевых ошибках"""
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                await message.reply_photo(
                    photo=image_bytes,
                    caption=caption,
                    api_kwargs={"read_timeout": 30}
                )
                return  # Успех
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_error = e
                logger.warning(f"🔄 Попытка {attempt}/{max_attempts} не удалась: {e}")
                await asyncio.sleep(2 ** attempt)  # 2с → 4с → 8с
            except Exception as e:
                # Не сетевая ошибка — сразу пробрасываем
                raise e

        # Все попытки исчерпаны
        raise last_error

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