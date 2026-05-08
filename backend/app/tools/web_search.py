from __future__ import annotations

import logging

import aiohttp

from app.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

QUERY_VARIANTS = ["", "参考", "设计", "trending", "examples"]


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "搜索互联网获取最新信息和参考资料。适用于查找设计趋势、风格参考、VI规范、"
        "配色方案、构图灵感等。返回结果包含标题、链接和内容摘要。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，用中文或英文",
            },
            "max_results": {
                "type": "integer",
                "description": "返回结果数量，默认5，最多10",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str = "", max_results: int = 5, **kwargs) -> ToolResult:
        api_key = kwargs.get("api_key", "")
        retry_count = int(kwargs.get("retry_count", 3))
        if not api_key:
            return ToolResult(
                content="搜索失败：未配置联网搜索API密钥，请在API管理中添加 provider_type=web_search 的提供商",
                meta={"error": "missing_api_key"},
            )

        content, sources, attempts, best = await _search_with_retry(
            api_key, query, max_results, retry_count, "search"
        )

        if not sources:
            return ToolResult(
                content=f"搜索未找到相关结果（尝试{attempts}次）", meta={"sources": [], "query": query, "attempts": attempts}
            )

        lines = []
        src_list = []
        for i, item in enumerate(sources[:max_results], 1):
            title = item.get("title", "无标题")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            lines.append(f"{i}. [{title}]({link})\n   {snippet}")
            src_list.append({"title": title, "url": link, "snippet": snippet})

        return ToolResult(
            content="\n\n".join(lines),
            meta={"sources": src_list, "query": query, "attempts": attempts, "best_attempt": best},
        )


async def _search_with_retry(
    api_key: str,
    query: str,
    max_results: int,
    retry_count: int,
    endpoint: str,
) -> tuple[str, list[dict], int, int]:
    url = f"https://google.serper.dev/{endpoint}"
    all_sources = []
    best_idx = 0

    for attempt in range(min(retry_count, len(QUERY_VARIANTS))):
        variant = QUERY_VARIANTS[attempt]
        q = f"{query} {variant}".strip() if variant else query
        sources = await _do_search(api_key, url, q, max_results)
        all_sources.append(sources)
        if len(sources) > len(all_sources[best_idx]):
            best_idx = attempt
        if len(sources) >= 3:
            break

    attempts = len(all_sources)
    if best_idx < len(all_sources) and all_sources[best_idx]:
        merged_sources = _merge_sources(all_sources)
        content = f"搜索完成（尝试{attempts}次）"
        return content, merged_sources, attempts, best_idx

    return "", [], attempts, -1


async def _do_search(api_key: str, url: str, query: str, max_results: int) -> list[dict]:
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    payload = {"q": query, "num": min(max_results, 10)}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("organic", data.get("images", []))
    except aiohttp.ClientError:
        return []


def _merge_sources(all_sources: list[list[dict]]) -> list[dict]:
    seen = set()
    merged = []
    for sources in all_sources:
        for s in sources:
            key = s.get("link", "") or s.get("imageUrl", "")
            if key and key not in seen:
                seen.add(key)
                merged.append(s)
    return merged
