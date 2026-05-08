from __future__ import annotations
from collections.abc import AsyncGenerator

import json

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
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
    ) -> dict:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
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

    async def chat_stream_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[dict, None]:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "tools": tools,
            "tool_choice": "auto",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=self._headers(), timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise LLMResponseError(f"LLM API error {resp.status}: {text}")
                    accumulated_tool_calls: dict[int, dict] = {}
                    async for line in resp.content:
                        line = line.decode("utf-8").strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                choices = chunk.get("choices") or [{}]
                                delta = choices[0].get("delta", {}) if choices else {}
                                finish_reason = choices[0].get("finish_reason", "")
                                content = delta.get("content") or ""
                                tool_calls_delta = delta.get("tool_calls") or []
                                usage = chunk.get("usage")

                                if content:
                                    yield {"type": "token", "content": content}

                                if tool_calls_delta:
                                    for tc_delta in tool_calls_delta:
                                        idx = tc_delta.get("index", 0)
                                        if idx not in accumulated_tool_calls:
                                            accumulated_tool_calls[idx] = {
                                                "id": tc_delta.get("id") or "",
                                                "function": {"name": "", "arguments": ""},
                                            }
                                        if tc_delta.get("id"):
                                            accumulated_tool_calls[idx]["id"] = tc_delta["id"]
                                        fn = tc_delta.get("function", {})
                                        if fn.get("name"):
                                            accumulated_tool_calls[idx]["function"]["name"] += fn["name"]
                                        if fn.get("arguments"):
                                            accumulated_tool_calls[idx]["function"]["arguments"] += fn["arguments"]

                                if usage:
                                    yield {
                                        "type": "usage",
                                        "tokens_in": usage.get("prompt_tokens", 0),
                                        "tokens_out": usage.get("completion_tokens", 0),
                                    }

                                if finish_reason == "tool_calls" and accumulated_tool_calls:
                                    resolved = []
                                    for tc in sorted(accumulated_tool_calls.values(), key=lambda x: x.get("id", "")):
                                        args_str = tc["function"]["arguments"]
                                        try:
                                            args = json.loads(args_str) if args_str else {}
                                        except json.JSONDecodeError:
                                            args = {}
                                        resolved.append({
                                            "id": tc["id"],
                                            "function": {
                                                "name": tc["function"]["name"],
                                                "arguments": args,
                                            },
                                        })
                                    yield {"type": "tool_calls", "tool_calls": resolved}

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
    def extract_tool_calls(response: dict) -> list[dict]:
        choices = response.get("choices", [])
        if choices:
            message = choices[0].get("message", {})
            return message.get("tool_calls") or []
        return []

    @staticmethod
    def estimate_tokens(text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)
