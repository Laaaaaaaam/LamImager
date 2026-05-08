from __future__ import annotations

import aiohttp

from app.tools.base import Tool, ToolResult


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
        if not api_key:
            return ToolResult(
                content="搜索失败：未配置联网搜索API密钥，请在API管理中添加 provider_type=web_search 的提供商",
                meta={"error": "missing_api_key"},
            )

        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "q": query,
            "num": min(max_results, 10),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        return ToolResult(
                            content=f"搜索返回错误 {resp.status}: {text[:200]}",
                            meta={"error": f"http_{resp.status}"},
                        )
                    data = await resp.json()
        except aiohttp.ClientError as e:
            return ToolResult(
                content=f"搜索连接失败: {e}",
                meta={"error": "connection_error"},
            )

        organic = data.get("organic", [])
        if not organic:
            return ToolResult(content="未找到相关搜索结果。", meta={"sources": [], "query": query})

        lines = []
        sources = []
        for i, item in enumerate(organic[:max_results], 1):
            title = item.get("title", "无标题")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            lines.append(f"{i}. [{title}]({link})\n   {snippet}")
            sources.append({"title": title, "url": link, "snippet": snippet})

        content = "\n\n".join(lines)
        return ToolResult(content=content, meta={"sources": sources, "query": query})
