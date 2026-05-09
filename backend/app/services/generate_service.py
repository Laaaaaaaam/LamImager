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
from app.services.settings_service import get_setting
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

    task_manager.update_task(session_id, TaskStatus.GENERATING, progress=0, total=data.image_count, message=f"生成中 0/{data.image_count}")

    try:
        all_image_urls, tokens_in, tokens_out = await generate_images_core(
            db=db,
            provider_id=image_provider_id,
            prompt=prompt,
            image_count=data.image_count,
            image_size=data.image_size,
            reference_images=data.reference_images if data.reference_images else None,
            reference_labels=data.reference_labels,
            negative_prompt=data.negative_prompt,
        )

        provider_result = await db.execute(select(ApiProvider).where(ApiProvider.id == image_provider_id))
        provider = provider_result.scalar_one_or_none()
        if not provider:
            raise ValueError("Image provider not found")

        actual_call_count = data.image_count if data.reference_images else 1
        cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=actual_call_count)

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

    except ValueError as e:
        task_manager.update_task(session_id, TaskStatus.ERROR, message=str(e))
        await add_system_message(db, session_id, str(e), message_type="error")
        return {"error": str(e)}
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


async def generate_images_core(
    db: AsyncSession,
    provider_id: str,
    prompt: str,
    image_count: int = 1,
    image_size: str = "1024x1024",
    reference_images: list[str] | None = None,
    reference_labels: list[str] | None = None,
    negative_prompt: str = "",
) -> tuple[list[str], int, int]:
    """Core image generation: provider lookup + decrypt + generate. No session-side effects."""
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError(f"Image provider not found: {provider_id}")

    api_key = decrypt(provider.api_key_enc)
    client = ImageClient(provider.base_url, api_key, provider.model_id)

    all_image_urls: list[str] = []
    tokens_in = 0
    tokens_out = 0

    if reference_images:
        concurrent_val = await get_setting(db, "max_concurrent")
        max_concurrent = concurrent_val.get("value", 5) if concurrent_val else 5
        semaphore = asyncio.Semaphore(max_concurrent)
        try:
            response = await client.chat_edit(
                prompt=prompt,
                images=reference_images,
                reference_labels=reference_labels,
            )
            urls = ImageClient.extract_images_from_chat(response)
            usage = response.get("usage", {})
            tokens_in += usage.get("prompt_tokens", 0)
            tokens_out += usage.get("completion_tokens", 0)
            if urls:
                all_image_urls.extend(urls)
                remaining = image_count - len(urls)
                if remaining > 0:
                    async def _chat_edit_one(idx):
                        async with semaphore:
                            try:
                                r = await client.chat_edit(prompt=prompt, images=reference_images, reference_labels=reference_labels)
                                return ImageClient.extract_images_from_chat(r), r.get("usage", {})
                            except Exception as e:
                                logger.error(f"Chat edit #{idx} failed: {e}")
                                return [], {}

                    tasks = [_chat_edit_one(i) for i in range(remaining)]
                    results_list = await asyncio.gather(*tasks)
                    for u_list, u_usage in results_list:
                        all_image_urls.extend(u_list)
                        tokens_in += u_usage.get("prompt_tokens", 0)
                        tokens_out += u_usage.get("completion_tokens", 0)
            else:
                raise ImageGenNotSupportedError("Chat API returned no images")
        except ImageGenNotSupportedError:
            pass
        except ImageGenError as e:
            logger.warning(f"Chat edit failed: {e}")

        if not all_image_urls:
            try:
                response = await client.edit(prompt=prompt, images=reference_images, n=1, size=image_size)
                urls = ImageClient.extract_images(response)
                all_image_urls.extend(urls)
                remaining = image_count - len(urls)
                if remaining > 0:
                    async def _edit_one(idx):
                        async with semaphore:
                            try:
                                r = await client.edit(prompt=prompt, images=reference_images, n=1, size=image_size)
                                return ImageClient.extract_images(r)
                            except Exception as e:
                                logger.error(f"Image edit #{idx} failed: {e}")
                                return []

                    tasks = [_edit_one(i) for i in range(remaining)]
                    results_list = await asyncio.gather(*tasks)
                    for u_list in results_list:
                        all_image_urls.extend(u_list)
            except Exception as e:
                logger.warning(f"Image edit not supported or failed: {e}")

        if not all_image_urls:
            prompt = await _apply_vision_fallback_core(db, prompt, reference_images)
            async def _generate_one(idx):
                async with semaphore:
                    try:
                        r = await client.generate(prompt=prompt, negative_prompt=negative_prompt, n=1, size=image_size)
                        return ImageClient.extract_images(r)
                    except Exception as e:
                        logger.error(f"Image generation #{idx} failed: {e}")
                        return []

            tasks = [_generate_one(i) for i in range(image_count)]
            results_list = await asyncio.gather(*tasks)
            for u_list in results_list:
                all_image_urls.extend(u_list)
    else:
        try:
            r = await client.generate(prompt=prompt, negative_prompt=negative_prompt, n=image_count, size=image_size)
            urls = ImageClient.extract_images(r)
            all_image_urls.extend(urls)
        except Exception as e:
            logger.error(f"Pure text generation failed: {e}")

    return all_image_urls, tokens_in, tokens_out


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


async def _apply_vision_fallback_core(
    db: AsyncSession,
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
            image_desc = await _describe_reference_images(db, llm_provider_id, reference_images, None)
            return f"{prompt}\n\n[参考图片视觉描述]:\n{image_desc}"
        except Exception as e:
            logger.warning(f"Vision fallback failed: {e}")

    return prompt


async def _execute_radiate(
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
    items = plan_meta.get("items") or []
    if isinstance(items, dict):
        items = []
    n_items = len(items) if items else 0
    if n_items == 0:
        logger.warning("_execute_radiate: no items in plan_meta, skipping radiate expansion")
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
    steps.append({"type": "radiate", "items": n_items, "grid": f"{cols}x{rows}"})

    style_desc = plan_meta.get("style", "")
    theme = plan_meta.get("overall_theme", "")
    if not style_desc:
        from app.models.message import Message
        msg_result = await db.execute(
            select(Message).where(
                Message.session_id == session_id,
                Message.role == "user",
            ).order_by(Message.created_at.desc()).limit(1)
        )
        user_msg = msg_result.scalars().first()
        user_text = user_msg.content if user_msg else data.prompt
        style_desc = _extract_style_from_text(user_text)
        theme = style_desc

    item_descs = ", ".join([it.get("prompt", "") for it in items[:8]])
    task_manager.update_task(session_id, TaskStatus.GENERATING, message=f"生成风格锚点图 ({cols}x{rows}, 4096x4096)")
    anchor_prompt = f"A {cols}x{rows} grid showing {item_descs}. {style_desc} style, matching visual theme. Each cell distinctly separated with clear boundaries. Consistent art style across all cells."

    try:
        anchor_sizes = ["4096x4096", "2048x2048", "1024x1024"]
        anchor_urls = []
        for sz in anchor_sizes:
            response = await client.generate(prompt=anchor_prompt, n=1, size=sz)
            anchor_urls = ImageClient.extract_images(response)
            if anchor_urls:
                break
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
                response = await client.chat_edit(
                    prompt=f"{item_prompt}. {style_desc} style.",
                    images=[grid_images[i]],
                )
                urls = ImageClient.extract_images_from_chat(response)
                if urls:
                    accumulated_images.extend(urls)
                    await add_system_message(db, session_id,
                        f"Agent 生成子项 {i+1}: {item_prompt[:40]}",
                        message_type="image",
                        metadata={"image_urls": urls},
                    )
                    steps.append({"type": "radiate_item", "index": i, "prompt": item_prompt})
            except Exception as e:
                logger.warning(f"Style anchor item #{i} failed: {e}")

        task_manager.update_task(session_id, TaskStatus.IDLE)
        return {
            "images": accumulated_images,
            "steps": steps,
            "strategy": "radiate",
            "cancelled": False,
        }

    except Exception as e:
        task_manager.update_task(session_id, TaskStatus.ERROR, message=str(e))
        await add_system_message(db, session_id, f"套图生成失败: {e}", message_type="error")
        return {"error": str(e)}


async def _build_agent_context(db: AsyncSession, session_id: str) -> list[dict]:
    import json
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc()).limit(8)
    )
    msgs = result.scalars().all()
    context = []
    for m in msgs:
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


def _extract_items_from_text(text: str) -> list[dict]:
    import re
    items = []
    emojis = {
        "开心": "happy expression", "难过": "sad expression", "生气": "angry expression",
        "愤怒": "angry furious expression",
        "惊讶": "surprised expression", "哭泣": "crying expression", "笑": "laughing smile expression",
        "爱": "love heart expression", "酷": "cool expression", "委屈": "upset expression",
        "晕": "dizzy expression", "害羞": "shy expression",
        "吃饭": "eating food expression", "睡觉": "sleeping expression",
        "胜利": "victory expression", "加油": "cheer expression", "疑问": "question expression",
        "无语": "speechless expression",
    }
    for kw, prompt in emojis.items():
        if kw in text:
            items.append({"prompt": prompt})
    if not items:
        count_match = re.search(r'(\d+)\s*[张张个]', text)
        if count_match:
            count = int(count_match.group(1))
            for i in range(count):
                items.append({"prompt": f"item {i+1}"})
    return items


def _extract_style_from_text(text: str) -> str:
    style_map = {
        "可爱": "cute kawaii chibi", "炫酷": "cool cyberpunk neon",
        "MC": "Minecraft pixel blocky", "像素": "pixel art retro game",
        "猫": "cat character", "狗": "dog character",
        "emoji": "emoji sticker", "表情": "emoji expression sticker",
        "水墨": "ink wash painting", "水彩": "watercolor painting",
        "赛博朋克": "cyberpunk neon futuristic",
    }
    for kw, style in style_map.items():
        if kw in text:
            return style
    return "digital art illustration"


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
            response = await client.chat_edit(
                prompt=item_prompt,
                images=[ref],
            )
            urls = ImageClient.extract_images_from_chat(response)
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

    image_provider_id = await _get_default_provider(db, "default_image_provider_id")
    if not image_provider_id:
        provider_result = await db.execute(
            select(ApiProvider).where(
                ApiProvider.provider_type == ProviderType.image_gen,
                ApiProvider.is_active == True,
            )
        )
        image_provider = provider_result.scalars().first()
        if image_provider:
            image_provider_id = image_provider.id

    # Direct radiate routing for 套图/表情包/系列/组 requests
    import re as _re
    _set_keywords = ["套图", "表情包", "表情", "套", "组图", "系列图", "图标集"]
    _is_set_request = any(kw in prompt for kw in _set_keywords)
    _count_m = _re.search(r'(\d+)\s*[张张个]', prompt)
    _n_items = int(_count_m.group(1)) if _count_m else 0
    if _is_set_request and _n_items >= 2:
        from app.models.plan_template import PlanTemplate
        tpl_result = await db.execute(
            select(PlanTemplate).where(
                PlanTemplate.name == "套图生成",
                PlanTemplate.is_builtin == True,
            )
        )
        radiate_template = tpl_result.scalar_one_or_none()
        if radiate_template:
            items = _extract_items_from_text(prompt)
            style = _extract_style_from_text(prompt)
            radiate_meta = {
                "items": items,
                "style": style,
                "overall_theme": prompt,
                "strategy": "radiate",
                "steps": radiate_template.steps or [],
            }
            logger.info(f"Direct radiate routing: {_n_items} items, style={style}")
            steps = [{"type": "radiate", "strategy": "radiate", "items": items}]
            result = await _execute_radiate(
                db, session_id, radiate_meta, data,
                task_manager, [], steps,
                llm_provider_id, 0, 0, 0.0,
            )
            if result:
                return result

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

    CORE_AGENT_TOOLS = ["generate_image", "plan"]
    all_tools = list(set(CORE_AGENT_TOOLS + (data.agent_tools or [])))

    async for event in run_agent_loop(
        db=db,
        provider_id=llm_provider_id,
        messages=messages,
        tools=all_tools,
        session_id=session_id,
        cancel_event=cancel_event,
    ):
        if event.type == "error":
            task_manager.update_task(session_id, TaskStatus.ERROR, message=event.error)
            final_output = f"Agent 执行失败: {event.error}"
            break
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
                t_in = event.meta.get("tokens_in", 0)
                t_out = event.meta.get("tokens_out", 0)
                if (t_in or t_out) and image_provider_id:
                    img_provider = await db.execute(select(ApiProvider).where(ApiProvider.id == image_provider_id))
                    img_prov = img_provider.scalar_one_or_none()
                    if img_prov:
                        img_cost = calc_cost(img_prov, tokens_in=t_in, tokens_out=t_out, call_count=len(urls))
                        await record_billing(db, session_id=session_id, provider_id=img_prov.id,
                            billing_type=img_prov.billing_type.value, tokens_in=t_in, tokens_out=t_out,
                            cost=img_cost, currency=img_prov.currency,
                            detail={"type": "image_gen", "agent": True, "image_count": len(urls)})
                        cost_total += img_cost
            if event.name == "generate_image" and event.meta and event.meta.get("grid_images"):
                grid_imgs = event.meta.get("grid_images", [])
                grid_config = event.meta.get("grid_config", {})
                result = await _expand_grid_images(
                    db, session_id, grid_imgs, grid_config,
                    task_manager, accumulated_images, steps,
                )
                if result:
                    return result
            if event.name == "plan" and event.meta and event.meta.get("strategy") == "radiate":
                items = event.meta.get("items", [])
                if not items:
                    from app.models.message import Message
                    msg_result = await db.execute(
                        select(Message).where(
                            Message.session_id == session_id,
                            Message.role == "user",
                        ).order_by(Message.created_at.desc()).limit(1)
                    )
                    user_msg = msg_result.scalars().first()
                    user_text = user_msg.content if user_msg else data.prompt
                    items = _extract_items_from_text(user_text)
                    if not items:
                        import re
                        count_m = re.search(r'(\d+)\s*[张张个]', user_text)
                        if count_m:
                            n = int(count_m.group(1))
                            items = [{"prompt": f"item {i+1}"} for i in range(n)]
                    event.meta["items"] = items
                if items:
                    with open("E:/LamImager/backend/radiate_debug.log", "a", encoding="utf-8") as f:
                        f.write(f"RADIATE: executing with {len(items)} items\n")
                    result = await _execute_radiate(
                        db, session_id, event.meta, data,
                        task_manager, accumulated_images, steps,
                        llm_provider_id, tokens_in, tokens_out, cost_total,
                    )
                    if result:
                        return result
                else:
                    with open("E:/LamImager/backend/radiate_debug.log", "a", encoding="utf-8") as f:
                        f.write("RADIATE: items empty, skipped\n")
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
        "images": accumulated_images,
    }
