import pytest
from services.queue_manager import QueueItem, GenerationQueue

@pytest.mark.asyncio
async def test_queue_add_and_size():
    """Базовый тест: очередь принимает элементы и меняет размер"""
    q = GenerationQueue()
    await q.start()

    # Мокаем Message, чтобы не запускать бота
    class FakeMsg:
        async def edit_text(self, text): pass

    item = QueueItem(
        user_id=123, prompt="test", payload={},
        message=FakeMsg(), progress_msg=FakeMsg(),
        callback=lambda p: None, usage_type="free"
    )

    await q.add_request(item)
    assert q.queue_size == 1

    await q.stop()