from __future__ import annotations
from collections.abc import AsyncGenerator

import aiohttp


class LLMError(Exception):
    pass


class LLMConnectionError(LLMError):
    pass


class LLMResponseError(LLMError):
    pass


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model_id: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> dict:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise LLMResponseError(f"LLM API error {resp.status}: {text}")
                    data = await resp.json()
                    return data
        except aiohttp.ClientError as e:
            raise LLMConnectionError(f"Connection error: {e}") from e

    async def chat_stream(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[tuple[str, dict | None], None]:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise LLMResponseError(f"LLM API error {resp.status}: {text}")
                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            import json
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices") or [{}]
                                delta = choices[0].get("delta", {}) if choices else {}
                                content = delta.get("content", "")
                                usage = chunk.get("usage")
                                usage_data = None
                                if usage:
                                    usage_data = {
                                        "prompt_tokens": usage.get("prompt_tokens", 0),
                                        "completion_tokens": usage.get("completion_tokens", 0),
                                        "total_tokens": usage.get("total_tokens", 0),
                                    }
                                if content or usage_data:
                                    yield content, usage_data
                            except json.JSONDecodeError:
                                continue
        except aiohttp.ClientError as e:
            raise LLMConnectionError(f"Connection error: {e}") from e

    async def test_connection(self) -> bool:
        try:
            result = await self.chat(
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            )
            return "choices" in result
        except LLMError:
            return False

    @staticmethod
    def extract_usage(response: dict) -> dict:
        usage = response.get("usage", {})
        return {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        }

    @staticmethod
    def extract_content(response: dict) -> str:
        choices = response.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
