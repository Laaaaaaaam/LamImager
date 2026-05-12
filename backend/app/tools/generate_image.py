from __future__ import annotations

import base64
import io
import logging

import aiohttp
from PIL import Image as PILImage

from app.tools.base import Tool, ToolResult
from app.utils.image_client import ImageClient

logger = logging.getLogger(__name__)


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
        reference_images: list[str] | None = None,
        reference_labels: list[dict] | None = None,
        grid_config: dict | None = None,
        **kwargs,
    ) -> ToolResult:
        from sqlalchemy.ext.asyncio import AsyncSession
        from app.services.generate_service import generate_images_core

        db: AsyncSession | None = kwargs.get("db")
        image_provider_id = kwargs.get("image_provider_id", "")
        image_size = kwargs.get("image_size", "1024x1024")
        session_id = kwargs.get("session_id", "")

        if not db:
            return ToolResult(
                content="生成失败：缺少数据库会话",
                meta={"error": "no_db_session"},
            )
        if not image_provider_id:
            return ToolResult(
                content="生成失败：未配置图像生成API，请在设置中配置默认图像提供商",
                meta={"error": "missing_image_provider"},
            )

        count = max(1, min(count, 4))

        logger.info(f"generate_image tool: reference_urls={'provided' if reference_urls else 'empty'}, reference_images={'provided' if reference_images else 'empty'}, count={count}")

        if grid_config:
            return await _generate_grid(db, image_provider_id, prompt, grid_config, image_size, reference_urls, session_id=session_id)

        reference_base64: list[str] = list(reference_images or [])
        if reference_urls:
            url_b64 = await ImageClient.urls_to_base64(reference_urls)
            reference_base64.extend(url_b64)

        try:
            urls, tokens_in, tokens_out = await generate_images_core(
                db=db,
                provider_id=image_provider_id,
                prompt=prompt,
                image_count=count,
                image_size=image_size,
                reference_images=reference_base64 if reference_base64 else None,
                reference_labels=reference_labels or None,
                session_id=session_id,
            )
        except Exception as e:
            logger.error(f"generate_image tool failed: {e}")
            return ToolResult(
                content=f"生成失败: {e}",
                meta={"error": str(e)},
            )

        if not urls:
            return ToolResult(
                content="生成失败：生图API未返回任何图片",
                meta={"error": "no_images"},
            )

        return ToolResult(
            content=f"已生成 {len(urls)} 张图片",
            meta={"image_urls": urls, "prompt": prompt, "count": count,
                  "tokens_in": tokens_in, "tokens_out": tokens_out},
        )


async def _generate_grid(
    db,
    image_provider_id: str,
    prompt: str,
    grid_config: dict,
    image_size: str,
    reference_urls: list[str] | None,
    session_id: str = "",
) -> ToolResult:
    cols = grid_config.get("cols", 2)
    rows = grid_config.get("rows", 2)
    grid_prompt = f"{prompt}. Split into {cols}x{rows} equal grid cells, each cell distinct, clean borders."

    reference_base64: list[str] = []
    if reference_urls:
        reference_base64 = await ImageClient.urls_to_base64(reference_urls)

    try:
        from app.services.generate_service import generate_images_core
        urls, tokens_in, tokens_out = await generate_images_core(
            db=db,
            provider_id=image_provider_id,
            prompt=grid_prompt,
            image_count=1,
            image_size=image_size,
            reference_images=reference_base64 if reference_base64 else None,
            session_id=session_id,
        )

        if not urls:
            return ToolResult(content="网格图生成失败：API未返回图片", meta={"error": "no_grid_image"})

        grid_url = urls[0]
        grid_b64 = grid_url
        if grid_b64.startswith("http"):
            async with aiohttp.ClientSession() as session:
                async with session.get(grid_b64, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        grid_b64 = base64.b64encode(data).decode("utf-8")
                        grid_b64 = f"data:image/png;base64,{grid_b64}"

        b64_data = grid_b64
        if b64_data.startswith("data:"):
            b64_data = b64_data.split(",", 1)[1]
        img_data = base64.b64decode(b64_data)
        img = PILImage.open(io.BytesIO(img_data))
        w, h = img.size
        cell_w = w // cols
        cell_h = h // rows

        grid_images = []
        for row in range(rows):
            for col in range(cols):
                left = col * cell_w
                top = row * cell_h
                cell = img.crop((left, top, left + cell_w, top + cell_h))
                buf = io.BytesIO()
                cell.save(buf, format="PNG")
                cell_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                grid_images.append(f"data:image/png;base64,{cell_b64}")

        return ToolResult(
            content=f"已生成 {cols}x{rows} 网格图，切分出 {len(grid_images)} 张子图",
            meta={
                "image_urls": [grid_url],
                "grid_images": grid_images,
                "grid_config": {"cols": cols, "rows": rows},
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            },
        )
    except Exception as e:
        logger.error(f"Grid generation failed: {e}")
        return ToolResult(content=f"网格图生成失败: {e}", meta={"error": str(e)})
