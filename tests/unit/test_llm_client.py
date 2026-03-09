"""Tests for the LLM client wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from content_farm.llm.client import LLMClient, LLMOutputError


class SampleOutput(BaseModel):
    name: str
    value: int


class TestLLMClient:
    @pytest.mark.asyncio
    async def test_generate_structured_returns_parsed(self) -> None:
        expected = SampleOutput(name="test", value=42)

        mock_response = MagicMock()
        mock_response.parsed_output = expected
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.messages.parse = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_instance

            client = LLMClient(api_key="test-key")
            result = await client.generate_structured(
                system="test system",
                user_prompt="test prompt",
                output_schema=SampleOutput,
            )

        assert result.name == "test"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_generate_structured_raises_on_none(self) -> None:
        mock_response = MagicMock()
        mock_response.parsed_output = None

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.messages.parse = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_instance

            client = LLMClient(api_key="test-key")
            with pytest.raises(LLMOutputError):
                await client.generate_structured(
                    system="test",
                    user_prompt="test",
                    output_schema=SampleOutput,
                )

    @pytest.mark.asyncio
    async def test_generate_text_returns_string(self) -> None:
        mock_block = MagicMock()
        mock_block.text = "Hello world"

        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5

        with patch("anthropic.AsyncAnthropic") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_instance

            client = LLMClient(api_key="test-key")
            result = await client.generate_text(
                system="test",
                user_prompt="test",
            )

        assert result == "Hello world"
