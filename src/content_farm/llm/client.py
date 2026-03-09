"""Thin async wrapper around the Anthropic SDK."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMOutputError(Exception):
    """Raised when the LLM fails to produce valid structured output."""


class LLMClient:
    """Async LLM client wrapping anthropic.AsyncAnthropic."""

    def __init__(self, api_key: str, max_retries: int = 3) -> None:
        self._client = anthropic.AsyncAnthropic(
            api_key=api_key,
            max_retries=max_retries,
        )

    async def generate_structured(
        self,
        *,
        system: str,
        user_prompt: str,
        output_schema: type[T],
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
    ) -> T:
        """Generate structured output using messages.parse() with Pydantic schema."""
        response = await self._client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=output_schema,
        )

        if response.parsed_output is None:
            raise LLMOutputError(
                f"Model returned None for schema {output_schema.__name__}"
            )

        logger.info(
            "LLM call: model=%s, input_tokens=%d, output_tokens=%d",
            model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return response.parsed_output

    async def generate_text(
        self,
        *,
        system: str,
        user_prompt: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
    ) -> str:
        """Generate plain text response."""
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = response.content[0].text if response.content else ""
        logger.info(
            "LLM call: model=%s, input_tokens=%d, output_tokens=%d",
            model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return text

    async def generate_json(
        self,
        *,
        system: str,
        user_prompt: str,
        json_schema: dict,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
    ) -> dict:
        """Generate structured output using raw JSON schema via output_config."""
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": json_schema,
                }
            },
        )

        text = response.content[0].text if response.content else "{}"
        logger.info(
            "LLM call: model=%s, input_tokens=%d, output_tokens=%d",
            model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return json.loads(text)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()
