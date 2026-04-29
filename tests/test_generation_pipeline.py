import pytest
from unittest.mock import AsyncMock, patch
from services.generation_pipeline import check_user_limits, submit_to_queue
from services.payload_builder import build_generation_payload
from utils.prompt_utils import extract_prompt, prepare_prompt

@pytest.mark.asyncio
async def test_check_user_limits_success():
    with patch("services.generation_pipeline.check_generation_limit", return_value=(True, "free")):
        mock_update = AsyncMock()
        result = await check_user_limits(mock_update, 123)
        assert result == "free"
        mock_update.message.reply_text.assert_not_called()

@pytest.mark.asyncio
async def test_check_user_limits_no_credits():
    with patch("services.generation_pipeline.check_generation_limit", return_value=(False, "no_credits")):
        mock_update = AsyncMock()
        result = await check_user_limits(mock_update, 123)
        assert result is None
        mock_update.message.reply_text.assert_called_once()

@pytest.mark.asyncio
async def test_extract_prompt_from_args():
    mock_ctx = AsyncMock()
    mock_ctx.args = ["cyberpunk", "city"]
    mock_update = AsyncMock()
    assert extract_prompt(mock_update, mock_ctx) == "cyberpunk city"

@pytest.mark.asyncio
async def test_prepare_prompt_no_cyrillic():
    mock_update = AsyncMock()
    assert await prepare_prompt(mock_update, "cat in hat") == "cat in hat"
    mock_update.message.reply_text.assert_not_called()