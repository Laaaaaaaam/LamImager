from __future__ import annotations

import asyncio
import base64

import aiohttp

from app.tools.base import Tool, ToolResult


class GenerateImageTool(Tool):
    name = "generate_image"
    description = (
        "调用图像生成API生成图片。可用于根据提示词生成单张或批量图片。"
        "可传入从 image_search 结果中选取的参考图URL列表 (reference_urls)，"
        "系统会自动转换为参考图传给生图模型。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "生图提示词，英文效果最佳。描述你想要的画面内容、风格、构图等。",
            },
            "count": {
                "type": "integer",
                "description": "生成图片数量，默认1，最多4",
                "default": 1,
            },
            "reference_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "参考图URL列表。从 image_search 工具返回的 sources[].image_url 中选取合适的URL传入。",
            },
        },
        "required": ["prompt"],
    }

    async def execute(
        self,
        prompt: str = "",
        count: int = 1,
        reference_urls: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        api_key = kwargs.get("image_api_key", "")
        base_url = kwargs.get("image_base_url", "")
        model_id = kwargs.get("image_model_id", "")
        image_size = kwargs.get("image_size", "1024x1024")

        if not api_key or not base_url:
            return ToolResult(
                content="生成失败：未配置图像生成API，请在设置中配置默认图像提供商",
                meta={"error": "missing_image_provider"},
            )

        from app.utils.image_client import ImageClient

        client = ImageClient(base_url, api_key, model_id)
        count = max(1, min(count, 4))

        reference_base64: list[str] = []
        if reference_urls:
            reference_base64 = await _urls_to_base64(reference_urls)

        async def generate_one(idx):
            try:
                if reference_base64:
                    response = await client.chat_edit(
                        prompt=prompt,
                        images=reference_base64,
                    )
                    return ImageClient.extract_images_from_chat(response)
                else:
                    response = await client.generate(
                        prompt=prompt,
                        n=1,
                        size=image_size,
                    )
                    return ImageClient.extract_images(response)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Image generation #{idx} failed: {e}")
                return []

        semaphore = asyncio.Semaphore(5)
        async def sem_generate(idx):
            async with semaphore:
                return await generate_one(idx)

        tasks = [sem_generate(i) for i in range(count)]
        results = await asyncio.gather(*tasks)

        all_urls = []
        for urls in results:
            all_urls.extend(urls)

        if not all_urls:
            return ToolResult(
                content="生成失败：生图API未返回任何图片",
                meta={"error": "no_images"},
            )

        return ToolResult(
            content=f"已生成 {len(all_urls)} 张图片",
            meta={"image_urls": all_urls, "prompt": prompt, "count": count},
        )


async def _urls_to_base64(urls: list[str]) -> list[str]:
    result = []
    async with aiohttp.ClientSession() as session:
        for url in urls[:6]:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        mimetype = resp.content_type or "image/png"
                        b64 = base64.b64encode(data).decode("utf-8")
                        result.append(f"data:{mimetype};base64,{b64}")
            except Exception:
                continue
    return result
