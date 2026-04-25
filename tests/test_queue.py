# test_queue.py
import asyncio
import logging
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

from services.queue_manager import GenerationQueue

# 🔥 Включаем дебаг-логи
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# 🎭 Простейший мок для сообщения (только то, что реально используется)
@dataclass
class MockMessage:
    from_user: 'MockUser'
    message_id: int = 999

    async def reply_text(self, text: str, **kwargs):
        logger.debug(f"💬 [MOCK reply_text] {text[:50]}")
        return self

    async def edit_text(self, text: str, **kwargs):
        logger.debug(f"✏️ [MOCK edit_text] {text[:50]}")
        return self

    async def reply_photo(self, photo: bytes, caption: str, **kwargs):
        logger.info(f"📸 [MOCK reply_photo] {len(photo)} байт, caption={caption[:30]}")
        return self


@dataclass
class MockUser:
    id: int
    first_name: str
    is_bot: bool = False


# 🎭 Моковая функция генерации (синхронная — для asyncio.to_thread)
def mock_generate(payload: dict) -> bytes:
    """Синхронная мока для тестов (совместима с asyncio.to_thread)"""
    model = payload.get("override_settings", {}).get("sd_model_checkpoint", "unknown")
    prompt = payload.get("prompt", "")
    logger.info(f"🎨 [MOCK] Генерация: модель={model.split('[')[0].strip()}, prompt={prompt[:30]}...")
    import time
    time.sleep(1)  # Имитация работы (1 сек)
    return b"fake_image_data"


async def test_queue():
    """Тестирует очередь с переключением моделей"""

    logger.info("🚀 Запуск теста очереди...")

    # 1. Создаём очередь
    queue = GenerationQueue()
    await queue.start()

    # 2. Формируем тестовые запросы (чередование моделей)
    test_cases = [
        # (user_id, model_checkpoint, prompt)
        (101, "boleromixPony_v233.safetensors [9223ce0e07]", "anime girl, white hair"),
        (102, "boleromixPony_v233.safetensors [9223ce0e07]", "cat, fantasy style"),  # та же модель
        (103, "ponyDiffusionV6XL_v6StartWithThisOne.safetensors [67ab2fd8ec]", "pony, rainbow"),  # другая
        (104, "boleromixPony_v233.safetensors [9223ce0e07]", "warrior, armor"),  # снова первая
        (105, "ponyDiffusionV6XL_v6StartWithThisOne.safetensors [67ab2fd8ec]", "unicorn, magic"),  # снова вторая
    ]

    logger.info("📥 Добавляем запросы в очередь...")

    for user_id, model_ckpt, prompt in test_cases:
        # Импортируем QueueItem внутри, чтобы не конфликтовало с моками
        from services.queue_manager import QueueItem

        item = QueueItem(
            user_id=user_id,
            prompt=prompt,
            payload={
                "prompt": prompt,
                "negative_prompt": "",
                "steps": 20,
                "cfg_scale": 7,
                "width": 512,
                "height": 768,
                "sampler_name": "DPM++ 2M Karras",
                "batch_size": 1,
                "override_settings": {"sd_model_checkpoint": model_ckpt}
            },
            message=MockMessage(from_user=MockUser(user_id, f"Test{user_id}")),
            progress_msg=MockMessage(from_user=MockUser(user_id, f"Test{user_id}")),
            callback=mock_generate
        )
        await queue.add_request(item)
        await asyncio.sleep(0.2)  # Небольшая задержка между запросами

    # 3. Ждём обработки (даём время на выполнение всех задач)
    logger.info("⏳ Ждём завершения обработки...")

    # Ждём, пока очередь не опустеет + небольшой буфер
    while not queue._queue.empty() or any(t.get_name() == "queue_worker" and not t.done()
                                          for t in asyncio.all_tasks() if t is not asyncio.current_task()):
        await asyncio.sleep(0.5)

    # Даём ещё 2 секунды на завершение последних операций
    await asyncio.sleep(2)

    # 4. Останавливаем очередь
    await queue.stop()

    # 5. Показываем статистику
    logger.info("📊 Статистика моделей:")
    for model, count in queue.stats.items():
        short_name = model.split('[')[0].strip() if model else "None"
        logger.info(f"   {short_name}: {count} запрос(ов)")

    logger.info("✅ Тест завершён успешно!")


if __name__ == "__main__":
    asyncio.run(test_queue())