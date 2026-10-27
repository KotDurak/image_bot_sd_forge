import asyncio
import logging
import time
import httpx
import base64
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from telegram import Message
from config import GATEWAY_URL  # 🔥 ИСПРАВЛЕНО: убрали 'settings', которого нет в твоем config.py
from models.generation_log import log_generation
from utils.tg_helpers import send_image_with_actions

logger = logging.getLogger(__name__)


# 🔥 ОСТАВЛЯЕМ QueueItem, чтобы generation_pipeline.py не сломался
@dataclass
class QueueItem:
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


class GatewayQueueManager:
    """Реализация очереди, которая общается с FastAPI Gateway"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=30.0),
            base_url=GATEWAY_URL
        )
        self._active_tasks = {}  # task_id -> QueueItem

    async def start(self):
        logger.info("🚀 Gateway Queue Manager запущен (режим Thin Client)")
        asyncio.create_task(self._monitor_loop(), name="gateway_monitor")

    async def stop(self):
        logger.info("🛑 Остановка Gateway Queue Manager...")
        await self.client.aclose()
        logger.info("✅ Gateway Queue Manager остановлен")

    async def add_request(self, item: QueueItem) -> bool:
        try:
            await self._update_progress(item, text="🎨 Отправляю задачу на сервер...")

            response = await self.client.post("/sdapi/v1/txt2img", json=item.payload)
            response.raise_for_status()
            task_id = response.json().get("task_id")

            if not task_id:
                raise ValueError("Gateway не вернул task_id")

            self._active_tasks[task_id] = item
            await self._update_progress(item, text="🎨 Задача в очереди сервера, ждем...")
            logger.info(f"✅ user_{item.user_id}: задача {task_id} успешно ушла на Gateway")
            return True

        except httpx.HTTPError as e:
            logger.error(f"❌ Ошибка связи с Gateway: {e}")
            await item.message.reply_text("😿 Ошибка связи с сервером генерации. Попробуй позже.")
            return False
        except Exception as e:
            logger.error(f"❌ Критическая ошибка отправки: {e}", exc_info=True)
            return False

    async def _monitor_loop(self):
        """Фоновый цикл опроса статуса задач на Gateway"""
        while True:
            if not self._active_tasks:
                await asyncio.sleep(2.0)
                continue

            for task_id in list(self._active_tasks.keys()):
                item = self._active_tasks[task_id]
                try:
                    resp = await self.client.get(f"/sdapi/v1/task/{task_id}")

                    if resp.status_code == 404:
                        await self._handle_error(item, "Задача потеряна на сервере")
                        del self._active_tasks[task_id]
                        continue

                    resp.raise_for_status()
                    res = resp.json()
                    status = res.get("status")

                    if status == "completed":
                        await self._handle_success(item, res)
                        del self._active_tasks[task_id]
                    elif status == "failed":
                        await self._handle_error(item, res.get("error", "Неизвестная ошибка сервера"))
                        del self._active_tasks[task_id]
                    elif status in ["queued", "processing"]:
                        # 🔥 ИСПРАВЛЕНИЕ: защита от None
                        prog = res.get("progress") or 0.0
                        eta = res.get("eta_relative") or 0

                        if prog > 0.01:
                            eta_text = f"⏱ ~{int(eta)} сек." if eta > 0 else "⏱ Завершение..."
                            text = f"🎨 Рисую... {int(prog * 100)}%\n{eta_text}"
                            await self._update_progress(item, text=text)

                except Exception as e:
                    logger.error(f"❌ Ошибка мониторинга задачи {task_id}: {e}")

            await asyncio.sleep(3.0)

    async def _handle_success(self, item: QueueItem, result: dict):
        try:
            image_b64 = result.get("image") or (result.get("images", [None])[0] if result.get("images") else None)
            if not image_b64:
                raise ValueError("Gateway вернул completed, но без изображения")

            image_bytes = base64.b64decode(image_b64)
            caption = (
                f"✨ *Генерация завершена!*\n\n"
                f"📝 *Использованные теги:*\n"
                f"`\n{item.prompt}\n`\n\n"
                f"💡 _Нажми на текст выше, чтобы скопировать теги для повторной генерации._"
            )
            await send_image_with_actions(item.message, image_bytes, caption)

            try:
                await log_generation(
                    user_id=item.user_id, prompt=item.prompt,
                    status="success", gen_time=time.time() - item.created_at
                )
            except Exception as e:
                logger.error(f"❌ Ошибка логирования: {e}")

            if item.show_ads:
                from services.ad_renderer import show_ad_after_generation
                asyncio.create_task(show_ad_after_generation(item.message, gen_id="gateway_mock"))

        except Exception as e:
            logger.error(f"❌ Ошибка обработки успеха: {e}", exc_info=True)
            await self._handle_error(item, "Ошибка при получении готового изображения")

    async def _handle_error(self, item: QueueItem, error_msg: str):
        await self._refund_if_needed(item)
        try:
            await log_generation(user_id=item.user_id, prompt=item.prompt, status="failed", error=error_msg)
        except Exception as e:
            logger.error(f"❌ Ошибка логирования ошибки: {e}")

        await item.message.reply_text(f"😿 Ошибка: {error_msg}. Кредит возвращён. Попробуй позже.")

    async def _update_progress(self, item: QueueItem, text: str):
        try:
            await item.progress_msg.edit_text(text)
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.debug(f"⚠️ Прогресс: {e}")

    async def _refund_if_needed(self, item: QueueItem):
        try:
            from models.user_quota import is_unlimited_user, refund_credit
            if await is_unlimited_user(item.user_id): return
            await refund_credit(item.user_id, item.usage_type)
        except Exception as e:
            logger.error(f"❌ Ошибка возврата кредита: {e}")


# ==============================================================================
# 🔥 МАГИЯ СОВМЕСТИМОСТИ: Чтобы ни один старый файл не упал при импорте!
# ==============================================================================

# 1. Для generation_pipeline.py (который делает: await generation_queue.add_request(item))
generation_queue = GatewayQueueManager()

# 2. Для main.py (который делает: from services.queue_manager import GenerationQueue)
GenerationQueue = GatewayQueueManager