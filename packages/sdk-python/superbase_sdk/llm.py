"""Lightweight LLM client for module-level inference."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around Anthropic-compatible API for module inference.

    Config via environment variables:
        API_BASE_URL: API endpoint (default: Anthropic proxy)
        API_KEY: API key
        MODEL_NAME: Model to use (default: mimo-v2.5-pro)
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._base_url = base_url or os.getenv("API_BASE_URL", "https://api.anthropic.com")
        self._api_key = api_key or os.getenv("API_KEY", "")
        self._model = model or os.getenv("MODEL_NAME", "mimo-v2.5-pro")
        self._client = None

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(
                base_url=self._base_url,
                api_key=self._api_key,
            )
        return self._client

    async def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Send a completion request and return the text response."""
        client = self._get_client()
        messages = [{"role": "user", "content": prompt}]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        return response.content[0].text if response.content else ""

    async def complete_json(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Complete and parse JSON response."""
        text = await self.complete(prompt, system, max_tokens, temperature)
        # Try to extract JSON from the response
        text = text.strip()
        if text.startswith("```"):
            # Remove markdown code fence
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)
