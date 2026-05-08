from __future__ import annotations

import asyncio
import base64
import io
import logging
from datetime import datetime

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider, ProviderType
from app.models.message import Message
from app.services.billing_service import record_billing, calc_cost
from app.schemas.session import GenerateRequest, MessageCreate
from app.schemas.prompt import PromptOptimizeRequest
from app.services.session_manager import add_message, add_system_message, message_to_response
from app.services.skill_engine import apply_skill, get_skill
from app.services.rule_engine import apply_rules, get_active_rules
from app.services.prompt_optimizer import optimize_prompt
from app.services.agent_service import run_agent_loop, AGENT_SYSTEM_PROMPT, ErrorEvent
from app.services.task_manager import TaskManager, TaskStatus
from app.utils.crypto import decrypt
from app.utils.image_client import ImageClient, ImageGenError, ImageGenNotSupportedError
from app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


async def handle_generate(db: AsyncSession, data: GenerateRequest) -> dict:
    session_id = data.session_id
    prompt = data.prompt

    task_manager = TaskManager()
    task_manager.update_task(session_id, TaskStatus.GENERATING, message="生成中")

    await add_message(db, session_id, MessageCreate(
        content=prompt,
        message_type="text",
        metadata={
            "negative_prompt": data.negative_prompt,
            "image_count": data.image_count,
            "image_size": data.image_size,
            "skill_ids": data.skill_ids,
            "has_reference_images": len(data.reference_images) > 0,
        },
    ))

    for skill_id in data.skill_ids:
        skill = await get_skill(db, skill_id)
        if skill:
            prompt = apply_skill(prompt, skill)

    rules = await get_active_rules(db)
    if rules:
        context = {"prompt": prompt, "negative_prompt": data.negative_prompt}
        result_context = apply_rules(context, rules)
        prompt = result_context.get("prompt", prompt)
        data.negative_prompt = result_context.get("negative_prompt", data.negative_prompt)

    multimodal_context = None

    if data.context_messages:
        context_parts = []
        multimodal_context = None
        for msg in data.context_messages[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                context_parts.append(f"[User]: {content}")
            elif role == "assistant":
                context_parts.append(f"[Assistant]: {content}")
        if any(msg.get("image_urls") for msg in data.context_messages):
            multimodal_context = _build_multimodal_context(data.context_messages)
        if context_parts:
            prompt = f"Context:\n{chr(10).join(context_parts)}\n\nCurrent request: {prompt}"

    if data.optimize_directions:
        provider_id = await _get_default_provider(db, "default_optimize_provider_id")
        if provider_id:
            try:
                task_manager.update_task(session_id, TaskStatus.OPTIMIZING, message="优化提示词中")
                direction = ",".join(data.optimize_directions)
                if data.custom_optimize_instruction:
                    direction += f",custom:{data.custom_optimize_instruction}"
                opt_result = await optimize_prompt(db, PromptOptimizeRequest(
                    prompt=prompt,
                    direction=direction,
                    llm_provider_id=provider_id,
                    multimodal_context=multimodal_context,
                    session_id=session_id,
                ))
                await add_system_message(db, session_id,
                    "提示词优化完成",
                    message_type="optimization",
                    metadata={
                        "original": opt_result.original,
                        "optimized": opt_result.optimized,
                        "direction": opt_result.direction,
                    },
                )
                prompt = opt_result.optimized
                task_manager.update_task(session_id, TaskStatus.GENERATING, message="生成中")
            except Exception as e:
                logger.warning(f"Prompt optimization failed: {e}")
                task_manager.update_task(session_id, TaskStatus.GENERATING, message="生成中")
                await add_system_message(db, session_id,
                    "提示词优化失败，使用原始提示词",
                    message_type="text",
                )

    image_provider_id = await _get_default_provider(db, "default_image_provider_id")
    if not image_provider_id:
        provider_result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.image_gen,
                ApiProvider.is_active == True,
            )
        )
        provider = provider_result.scalars().first()
        if not provider:
            task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置图像生成API")
            await add_system_message(db, session_id, "未配置图像生成API，请在API管理中添加", message_type="error")
            return {"error": "No image provider configured"}
        image_provider_id = provider.id

    provider_result = await db.execute(select(ApiProvider).where(ApiProvider.id == image_provider_id))
    provider = provider_result.scalar_one_or_none()
    if not provider:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="图像生成API未找到")
        await add_system_message(db, session_id, "图像生成API未找到", message_type="error")
        return {"error": "Image provider not found"}

    try:
        api_key = decrypt(provider.api_key_enc)
    except Exception as e:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="API密钥解密失败")
        await add_system_message(db, session_id, "API密钥解密失败，请重新在API管理中配置密钥（机器指纹可能已变更）", message_type="error")
        return {"error": f"API key decryption failed: {e}"}

    client = ImageClient(provider.base_url, api_key, provider.model_id)

    try:
        all_image_urls = []
        semaphore = asyncio.Semaphore(5)
        task_manager.update_task(session_id, TaskStatus.GENERATING, progress=0, total=data.image_count, message=f"生成中 0/{data.image_count}")

        if data.reference_images:
            chat_edit_usage = {}
            result = await _generate_with_references(
                db, session_id, client, provider, prompt, data, all_image_urls, semaphore, chat_edit_usage
            )
            if result:
                return result
            tokens_in = chat_edit_usage.get("tokens_in", 0)
            tokens_out = chat_edit_usage.get("tokens_out", 0)
        else:
            tokens_in = 0
            tokens_out = 0
            async def generate_one(idx):
                async with semaphore:
                    try:
                        response = await client.generate(
                            prompt=prompt,
                            negative_prompt=data.negative_prompt,
                            n=1,
                            size=data.image_size,
                        )
                        return ImageClient.extract_images(response)
                    except Exception as e:
                        logger.error(f"Image generation #{idx} failed: {e}")
                        return []

            tasks = [generate_one(i) for i in range(data.image_count)]
            results = await asyncio.gather(*tasks)
            for urls in results:
                all_image_urls.extend(urls)

        cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=data.image_count)

        await record_billing(
            db,
            session_id=session_id,
            provider_id=provider.id,
            billing_type=provider.billing_type.value,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            currency=provider.currency,
            detail={"type": "image_gen", "prompt": prompt[:200], "image_count": data.image_count, "image_size": data.image_size},
        )

        await add_system_message(db, session_id,
            f"已生成{len(all_image_urls)} 张图片",
            message_type="image",
            metadata={
                "image_urls": all_image_urls,
                "prompt": prompt,
                "negative_prompt": data.negative_prompt,
                "image_size": data.image_size,
                "cost": cost,
            },
        )

        task_manager.update_task(session_id, TaskStatus.IDLE)

        return {
            "image_urls": all_image_urls,
            "cost": cost,
            "prompt": prompt,
        }

    except Exception as e:
        import traceback
        logger.error(f"handle_generate failed: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        task_manager.update_task(session_id, TaskStatus.ERROR, message=str(e))
        await add_system_message(db, session_id, f"生成失败: {type(e).__name__}: {e}", message_type="error")
        return {"error": str(e)}


async def _get_default_provider(db: AsyncSession, setting_key: str) -> str | None:
    from app.services.settings_service import get_setting
    result = await get_setting(db, setting_key)
    if result and isinstance(result, dict):
        return result.get("provider_id")
    return None


async def _describe_reference_images(db: AsyncSession, provider_id: str, reference_images: list[str], session_id: str | None = None) -> str:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError("LLM provider not found")

    try:
        api_key = decrypt(provider.api_key_enc)
    except Exception as e:
        raise ValueError(f"LLM API key decryption failed: {e}") from e

    client = LLMClient(provider.base_url, api_key, provider.model_id)

    content_parts: list[dict] = []
    if len(reference_images) == 1:
        content_parts.append({
            "type": "text",
            "text": "请详细描述这张参考图片的视觉内容，包括：主体/人物、风格、色彩搭配、构图方式、光线条件、氛围、背景、纹理材质等所有视觉细节。只描述你看到的内容，不要添加解释或评论。用中文回答。",
        })
    else:
        content_parts.append({
            "type": "text",
            "text": f"请分别描述以下{len(reference_images)}张参考图片的视觉内容，每张图片包括：主体/人物、风格、色彩搭配、构图方式、光线条件、氛围、背景、纹理材质等所有视觉细节。最后总结这些图片的共同风格特征。只描述你看到的内容，不要添加解释或评论。用中文回答。",
        })

    for img in reference_images:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": img, "detail": "auto"},
        })

    messages = [{"role": "user", "content": content_parts}]

    response = await client.chat(messages, temperature=0.3, max_tokens=3000)
    description = LLMClient.extract_content(response)

    tokens_in = response.get("usage", {}).get("prompt_tokens", 0)
    tokens_out = response.get("usage", {}).get("completion_tokens", 0)

    cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=1)

    await record_billing(
        db,
        session_id=session_id,
        provider_id=provider.id,
        billing_type=provider.billing_type.value,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        currency=provider.currency,
        detail={"type": "vision", "image_count": len(reference_images)},
    )

    return description


async def _generate_with_references(
    db: AsyncSession,
    session_id: str,
    client: ImageClient,
    provider: ApiProvider,
    prompt: str,
    data: GenerateRequest,
    all_image_urls: list[str],
    semaphore: asyncio.Semaphore,
    chat_edit_tokens: dict,
) -> dict | None:
    try:
        response = await client.chat_edit(
            prompt=prompt,
            images=data.reference_images,
            reference_labels=data.reference_labels,
        )
        urls = ImageClient.extract_images_from_chat(response)
        usage = response.get("usage", {})
        chat_edit_tokens["tokens_in"] = chat_edit_tokens.get("tokens_in", 0) + usage.get("prompt_tokens", 0)
        chat_edit_tokens["tokens_out"] = chat_edit_tokens.get("tokens_out", 0) + usage.get("completion_tokens", 0)
        if urls:
            all_image_urls.extend(urls)
            await add_system_message(db, session_id,
                f"使用多模态图生图模式（Chat API），已参考 {len(data.reference_images)} 张图片",
                message_type="text",
            )

            remaining = data.image_count - len(urls)
            if remaining > 0:
                async def chat_edit_one(idx):
                    async with semaphore:
                        try:
                            response = await client.chat_edit(
                                prompt=prompt,
                                images=data.reference_images,
                                reference_labels=data.reference_labels,
                            )
                            urls_result = ImageClient.extract_images_from_chat(response)
                            c_usage = response.get("usage", {})
                            chat_edit_tokens["tokens_in"] = chat_edit_tokens.get("tokens_in", 0) + c_usage.get("prompt_tokens", 0)
                            chat_edit_tokens["tokens_out"] = chat_edit_tokens.get("tokens_out", 0) + c_usage.get("completion_tokens", 0)
                            return urls_result
                        except Exception as e:
                            logger.error(f"Chat edit #{idx} failed: {e}")
                            return []

                tasks = [chat_edit_one(i) for i in range(remaining)]
                results = await asyncio.gather(*tasks)
                for u in results:
                    all_image_urls.extend(u)

            return None
        else:
            raise ImageGenNotSupportedError("Chat API returned no images")
    except ImageGenNotSupportedError as e:
        logger.info(f"Chat edit not available: {e}")
    except ImageGenError as e:
        logger.warning(f"Chat edit via {provider.model_id} failed: {e}")

    try:
        response = await client.edit(
            prompt=prompt,
            images=data.reference_images,
            n=1,
            size=data.image_size,
        )
        urls = ImageClient.extract_images(response)
        all_image_urls.extend(urls)
        await add_system_message(db, session_id,
            f"使用原生图生图模式（Edits API），已参考 {len(data.reference_images)} 张图片",
            message_type="text",
        )

        remaining = data.image_count - len(urls)
        if remaining > 0:
            async def edit_one(idx):
                async with semaphore:
                    try:
                        response = await client.edit(
                            prompt=prompt,
                            images=data.reference_images,
                            n=1,
                            size=data.image_size,
                        )
                        return ImageClient.extract_images(response)
                    except Exception as e:
                        logger.error(f"Image edit #{idx} failed: {e}")
                        return []

            tasks = [edit_one(i) for i in range(remaining)]
            results = await asyncio.gather(*tasks)
            for urls in results:
                all_image_urls.extend(urls)

        return None

    except ImageGenError as e:
        logger.warning(f"Image edit API not supported by {provider.model_id}: {e}")
        await add_system_message(db, session_id,
            f"当前模型 {provider.model_id} 不支持原生图生图，降级为视觉分析模式",
            message_type="text",
        )

        prompt = await _apply_vision_fallback(db, session_id, prompt, data.reference_images)

        async def generate_one(idx):
            async with semaphore:
                try:
                    response = await client.generate(
                        prompt=prompt,
                        negative_prompt=data.negative_prompt,
                        n=1,
                        size=data.image_size,
                    )
                    return ImageClient.extract_images(response)
                except Exception as e:
                    logger.error(f"Image generation #{idx} failed: {e}")
                    return []

        tasks = [generate_one(i) for i in range(data.image_count)]
        results = await asyncio.gather(*tasks)
        for urls in results:
            all_image_urls.extend(urls)

        return None


async def _apply_vision_fallback(
    db: AsyncSession,
    session_id: str,
    prompt: str,
    reference_images: list[str],
) -> str:
    llm_provider_id = await _get_default_provider(db, "default_optimize_provider_id")
    if not llm_provider_id:
        provider_result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.llm,
                ApiProvider.is_active == True,
            )
        )
        llm_provider = provider_result.scalars().first()
        if llm_provider:
            llm_provider_id = llm_provider.id

    if llm_provider_id:
        try:
            image_desc = await _describe_reference_images(db, llm_provider_id, reference_images, session_id)
            await add_system_message(db, session_id,
                f"已分析 {len(reference_images)} 张参考图片并融入提示词",
                message_type="text",
                metadata={"image_descriptions": image_desc},
            )
            return f"{prompt}\n\n[参考图片视觉描述]:\n{image_desc}"
        except Exception as e:
            logger.warning(f"Vision fallback failed: {e}")
            await add_system_message(db, session_id,
                "参考图片视觉分析失败，将仅使用文本提示词。请确保配置了支持视觉的LLM。",
                message_type="text",
            )

    return prompt


async def _execute_style_anchor(
    db: AsyncSession,
    session_id: str,
    plan_meta: dict,
    data: GenerateRequest,
    task_manager: TaskManager,
    accumulated_images: list[str],
    steps: list[dict],
    llm_provider_id: str,
    tokens_in: int,
    tokens_out: int,
    cost_total: float,
) -> dict | None:
    items = plan_meta.get("items", data.agent_tools)
    if isinstance(items, dict):
        items = []
    n_items = len(items) if items else 0
    if n_items == 0:
        return None

    image_provider_id = await _get_default_provider(db, "default_image_provider_id")
    if not image_provider_id:
        result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.image_gen,
                ApiProvider.is_active == True,
            )
        )
        provider = result.scalars().first()
        if provider:
            image_provider_id = provider.id

    if not image_provider_id:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置图像生成API")
        return {"error": "No image provider"}

    provider_result = await db.execute(select(ApiProvider).where(ApiProvider.id == image_provider_id))
    provider = provider_result.scalar_one_or_none()
    if not provider:
        return {"error": "Image provider not found"}

    try:
        api_key = decrypt(provider.api_key_enc)
    except Exception as e:
        return {"error": f"Image key decrypt failed: {e}"}

    client = ImageClient(provider.base_url, api_key, provider.model_id)

    cols, rows = _compute_grid_config(n_items)
    steps.append({"type": "style_anchor", "items": n_items, "grid": f"{cols}x{rows}"})

    style_desc = plan_meta.get("style", plan_meta.get("template_name", ""))
    theme = plan_meta.get("overall_theme", "")

    task_manager.update_task(session_id, TaskStatus.GENERATING, message=f"生成风格锚点图 ({cols}x{rows})")
    anchor_prompt = f"A {cols}x{rows} grid layout of {n_items} items in {style_desc} style. {theme}. Each cell clearly separated, consistent unified style throughout the entire grid."

    try:
        response = await client.generate(prompt=anchor_prompt, n=1, size="1024x1024")
        anchor_urls = ImageClient.extract_images(response)
        if not anchor_urls:
            return {"error": "Failed to generate anchor grid"}

        anchor_url = anchor_urls[0]
        accumulated_images.append(anchor_url)
        await add_system_message(db, session_id,
            f"Agent 生成了风格锚点网格图 ({cols}x{rows})",
            message_type="image",
            metadata={"image_urls": [anchor_url]},
        )

        task_manager.set_checkpoint_state(session_id, {"step": "anchor_grid", "image_url": anchor_url, "cols": cols, "rows": rows})

        grid_images = await _crop_grid(anchor_url, cols, rows)
        if not grid_images or len(grid_images) < n_items:
            return {"error": f"Grid crop failed: got {len(grid_images)} cells, need {n_items}"}

        for i in range(n_items):
            item = items[i] if i < len(items) else {}
            item_prompt = item.get("prompt", f"item {i+1}")
            task_manager.update_task(session_id, TaskStatus.GENERATING,
                progress=i + 1, total=n_items,
                message=f"生成子项 {i + 1}/{n_items}: {item_prompt[:30]}")

            try:
                response = await client.generate(
                    prompt=f"{item_prompt}. {style_desc} style.",
                    n=1,
                    size="1024x1024",
                    reference_images=[grid_images[i]],
                )
                urls = ImageClient.extract_images(response)
                if urls:
                    accumulated_images.extend(urls)
                    await add_system_message(db, session_id,
                        f"Agent 生成子项 {i+1}: {item_prompt[:40]}",
                        message_type="image",
                        metadata={"image_urls": urls},
                    )
                    steps.append({"type": "style_anchor_item", "index": i, "prompt": item_prompt})
            except Exception as e:
                logger.warning(f"Style anchor item #{i} failed: {e}")

        task_manager.update_task(session_id, TaskStatus.IDLE)
        return {
            "images": accumulated_images,
            "steps": steps,
            "strategy": "style_anchor",
            "cancelled": False,
        }

    except Exception as e:
        task_manager.update_task(session_id, TaskStatus.ERROR, message=str(e))
        await add_system_message(db, session_id, f"套图生成失败: {e}", message_type="error")
        return {"error": str(e)}


async def _build_agent_context(db: AsyncSession, session_id: str) -> list[dict]:
    import json
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc()).limit(10)
    )
    msgs = result.scalars().all()
    context = []
    for m in msgs[-8:]:
        if m.role in ("user", "assistant") and m.message_type in ("text", "agent"):
            content = m.content[:500] if m.content else ""
            if m.message_type == "agent" and m.metadata_:
                try:
                    import json
                    meta = json.loads(m.metadata_) if isinstance(m.metadata_, str) else m.metadata_
                    content = meta.get("final_output", content)[:500]
                except Exception:
                    pass
            if content.strip():
                context.append({"role": m.role.value if hasattr(m.role, "value") else m.role, "content": content})
    return context


def _compute_grid_config(n: int) -> tuple[int, int]:
    if n <= 2:
        return 1, n
    elif n <= 4:
        return 2, (n + 1) // 2
    elif n <= 9:
        return 3, (n + 2) // 3
    else:
        return 4, (n + 3) // 4


async def _expand_grid_images(
    db: AsyncSession,
    session_id: str,
    grid_images: list[str],
    grid_config: dict,
    task_manager: TaskManager,
    accumulated_images: list[str],
    steps: list[dict],
) -> dict | None:
    n = len(grid_images)
    if n == 0:
        return None
    cols = grid_config.get("cols", 2)

    image_provider_id = await _get_default_provider(db, "default_image_provider_id")
    if not image_provider_id:
        result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.image_gen,
                ApiProvider.is_active == True,
            )
        )
        p = result.scalars().first()
        if p:
            image_provider_id = p.id

    if not image_provider_id:
        return None

    provider_result = await db.execute(select(ApiProvider).where(ApiProvider.id == image_provider_id))
    provider = provider_result.scalar_one_or_none()
    if not provider:
        return None

    try:
        api_key = decrypt(provider.api_key_enc)
    except Exception:
        return None

    client = ImageClient(provider.base_url, api_key, provider.model_id)

    for i in range(n):
        ref = grid_images[i]
        task_manager.update_task(session_id, TaskStatus.GENERATING,
            progress=i + 1, total=n,
            message=f"展开子项 {i + 1}/{n}")

        row = i // cols
        col = i % cols
        item_prompt = f"grid cell ({row+1},{col+1}), consistent style with reference"

        try:
            response = await client.generate(
                prompt=item_prompt,
                n=1,
                size="1024x1024",
                reference_images=[ref],
            )
            urls = ImageClient.extract_images(response)
            if urls:
                accumulated_images.extend(urls)
                await add_system_message(db, session_id,
                    f"Agent 展开子项 {i+1}/{n}",
                    message_type="image",
                    metadata={"image_urls": urls},
                )
                steps.append({"type": "grid_expand", "index": i, "row": row, "col": col})
        except Exception as e:
            logger.warning(f"Grid expand #{i} failed: {e}")

    task_manager.update_task(session_id, TaskStatus.IDLE)
    return {
        "images": accumulated_images,
        "steps": steps,
        "strategy": "grid_expand",
        "cancelled": False,
    }


async def _crop_grid(image_url: str, cols: int, rows: int) -> list[str]:
    try:
        from PIL import Image as PILImage
        import base64, io
        if image_url.startswith("data:"):
            b64_data = image_url.split(",", 1)[1]
        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    data = await resp.read()
                    b64_data = base64.b64encode(data).decode("utf-8")
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
        return grid_images
    except Exception:
        return []


def _build_multimodal_context(messages: list[dict]) -> list[dict]:
    content_parts: list[dict] = []
    content_parts.append({
        "type": "text",
        "text": "以下是对话上下文中的图片，供你参考以理解当前任务的视觉风格和内容：",
    })
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            content_parts.append({"type": "text", "text": f"[User]: {content}"})
        elif role == "assistant":
            content_parts.append({"type": "text", "text": f"[Assistant]: {content}"})
        for img_url in (msg.get("image_urls") or []):
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": img_url, "detail": "auto"},
            })
    return content_parts


async def handle_agent_generate(db: AsyncSession, data: GenerateRequest) -> dict:
    session_id = data.session_id
    prompt = data.prompt

    task_manager = TaskManager()
    task_manager.update_task(session_id, TaskStatus.GENERATING, message="Agent 执行中")

    await add_message(db, session_id, MessageCreate(
        content=prompt,
        message_type="text",
        metadata={"agent_mode": True, "agent_tools": data.agent_tools, "agent_plan_strategy": data.agent_plan_strategy},
    ))

    llm_provider_id = await _get_default_provider(db, "default_optimize_provider_id")
    if not llm_provider_id:
        provider_result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.llm,
                ApiProvider.is_active == True,
            )
        )
        llm_provider = provider_result.scalars().first()
        if llm_provider:
            llm_provider_id = llm_provider.id

    if not llm_provider_id:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置LLM")
        await add_system_message(db, session_id, "未配置LLM，请先在API管理中添加", message_type="error")
        return {"error": "No LLM provider configured"}

    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        history = await _build_agent_context(db, session_id)
        if history:
            messages = [{"role": "system", "content": AGENT_SYSTEM_PROMPT}] + history + [{"role": "user", "content": prompt}]
    except Exception:
        pass

    steps = []
    final_output = ""
    tokens_in = 0
    tokens_out = 0
    cost_total = 0.0
    cancelled = False
    accumulated_images: list[str] = []

    cancel_event = task_manager.get_cancel_event(session_id)

    async for event in run_agent_loop(
        db=db,
        provider_id=llm_provider_id,
        messages=messages,
        tools=data.agent_tools,
        session_id=session_id,
        cancel_event=cancel_event,
    ):
        if event.type == "error":
            task_manager.update_task(session_id, TaskStatus.ERROR, message=event.error)
            await add_system_message(db, session_id, f"Agent 执行失败: {event.error}", message_type="error")
            return {"error": event.error}
        elif event.type == "cancelled":
            cancelled = True
            final_output = event.partial_output
            tokens_in = event.tokens_in
            tokens_out = event.tokens_out
            break
        elif event.type == "tool_call":
            steps.append({"type": "tool_call", "name": event.name, "args": event.args})
        elif event.type == "tool_result":
            steps.append({"type": "tool_result", "name": event.name, "content": event.content[:500]})
            if event.name == "generate_image" and event.meta and event.meta.get("image_urls"):
                urls = event.meta.get("image_urls", [])
                accumulated_images.extend(urls)
                await add_system_message(db, session_id,
                    f"Agent 生成了 {len(urls)} 张图片",
                    message_type="image",
                    metadata={"image_urls": urls},
                )
            if event.name == "generate_image" and event.meta and event.meta.get("grid_images"):
                grid_imgs = event.meta.get("grid_images", [])
                grid_config = event.meta.get("grid_config", {})
                result = await _expand_grid_images(
                    db, session_id, grid_imgs, grid_config,
                    task_manager, accumulated_images, steps,
                )
                if result:
                    return result
            if event.name == "plan" and event.meta and event.meta.get("strategy") == "style_anchor":
                result = await _execute_style_anchor(
                    db, session_id, event.meta, data,
                    task_manager, accumulated_images, steps,
                    llm_provider_id, tokens_in, tokens_out, cost_total,
                )
                if result:
                    return result
        elif event.type == "token":
            final_output += event.content
        elif event.type == "done":
            tokens_in = event.tokens_in
            tokens_out = event.tokens_out
            cost_total = event.cost

    cancel_label = " (已取消)" if cancelled else ""
    await add_system_message(db, session_id,
        (final_output.strip() or "Agent 执行完成") + cancel_label,
        message_type="agent",
        metadata={
            "steps": steps,
            "final_output": final_output,
            "images": accumulated_images,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": cost_total,
            "cancelled": cancelled,
        },
    )

    task_manager.update_task(session_id, TaskStatus.IDLE)

    return {
        "output": final_output,
        "steps": steps,
        "cost": cost_total,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cancelled": cancelled,
    }
