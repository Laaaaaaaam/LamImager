from __future__ import annotations

import aiohttp

from app.tools.base import Tool, ToolResult


class ImageSearchTool(Tool):
    name = "image_search"
    description = (
        "搜索互联网上的图片，获取设计参考图、风格情绪板、材质参考等。"
        "返回图片的标题、URL、缩略图和来源信息，可用于后续图像生成的视觉参考。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，用中文或英文描述想要搜索的图片类型",
            },
            "max_results": {
                "type": "integer",
                "description": "返回图片数量，默认5，最多10",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str = "", max_results: int = 5, **kwargs) -> ToolResult:
        api_key = kwargs.get("api_key", "")
        if not api_key:
            return ToolResult(
                content="图片搜索失败：未配置搜索API密钥，请在API管理中添加 provider_type=tool 的提供商",
                meta={"error": "missing_api_key"},
            )

        url = "https://google.serper.dev/images"
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
                            content=f"图片搜索返回错误 {resp.status}: {text[:200]}",
                            meta={"error": f"http_{resp.status}"},
                        )
                    data = await resp.json()
        except aiohttp.ClientError as e:
            return ToolResult(
                content=f"图片搜索连接失败: {e}",
                meta={"error": "connection_error"},
            )

        images = data.get("images", [])
        if not images:
            return ToolResult(content="未找到相关图片。", meta={"sources": [], "query": query})

        lines = []
        sources = []
        for i, item in enumerate(images[:max_results], 1):
            title = item.get("title", "无标题")
            image_url = item.get("imageUrl", "")
            source_url = item.get("link", "")
            lines.append(f"{i}. {title}\n   图片: {image_url}\n   来源: {source_url}")
            sources.append({
                "title": title,
                "image_url": image_url,
                "source_url": source_url,
            })

        content = "\n\n".join(lines)
        return ToolResult(
            content=content,
            meta={"sources": sources, "query": query, "image_count": len(sources)},
        )
