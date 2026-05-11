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
from app.services.api_manager import resolve_provider_vendor
from app.utils.image_client import ImageClient, ImageGenError, ImageGenNotSupportedError
from app.utils.llm_client import LLMClient
from app.services.agent_intent_service import (
    AgentIntent,
    STRATEGY_MAP,
    TASK_TYPE_LABELS,
    parse_agent_intent,
    resolve_context_references,
    execute_multi_independent,
    validate_agent_result,
    _generate_iterative_steps,
    _generate_radiate_params,
    _extract_items_from_text,
    _extract_style_from_text,
    _extract_context_image_urls,
    has_search_intent,
    hybrid_parse_intent,
)
from app.services.plan_executor import execute_parallel, execute_iterative

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
            session_id=session_id,
        )

        actual_count = len(all_image_urls)
        task_manager.update_task(session_id, TaskStatus.GENERATING, progress=actual_count, total=actual_count, message=f"生成完成 {actual_count}/{actual_count}")

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
    session_id: str | None = None,
) -> tuple[list[str], int, int]:
    """Core image generation: provider lookup + decrypt + generate. No session-side effects."""
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError(f"Image provider not found: {provider_id}")

    base_url, api_key = await resolve_provider_vendor(db, provider)
    client = ImageClient(base_url, api_key, provider.model_id)

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
            prompt = await _apply_vision_fallback_core(db, prompt, reference_images, session_id=session_id)
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
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        raise ValueError(f"LLM API key decryption failed: {e}") from e

    client = LLMClient(base_url, api_key, provider.model_id)

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
    session_id: str | None = None,
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
    intermediate_images: list[str],
    steps: list[dict],
    llm_provider_id: str,
    tokens_in: int,
    tokens_out: int,
    cost_total: float,
    reference_images: list[str] | None = None,
    reference_labels: list[dict] | None = None,
) -> dict | None:
    items = plan_meta.get("items") or []
    if isinstance(items, dict):
        logger.warning("_execute_radiate: items is dict instead of list, discarding")
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
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        return {"error": f"Image key decrypt failed: {e}"}

    client = ImageClient(base_url, api_key, provider.model_id)

    cols, rows = _compute_grid_config(n_items)
    steps.append({"type": "tool_result", "name": "radiate", "args": {"items": n_items, "grid": f"{cols}x{rows}"}, "content": f"锚点网格 {cols}x{rows}, {n_items} 个子项"})

    style_desc = plan_meta.get("style", "")
    theme = plan_meta.get("overall_theme", "")
    if not style_desc:
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
        intermediate_images.append(anchor_url)
        accumulated_images.append(anchor_url)

        anchor_usage = response.get("usage", {}) if isinstance(response, dict) else {}
        anchor_t_in = anchor_usage.get("prompt_tokens", 0)
        anchor_t_out = anchor_usage.get("completion_tokens", 0)
        anchor_cost = calc_cost(provider, tokens_in=anchor_t_in, tokens_out=anchor_t_out, call_count=1)
        await record_billing(db, session_id=session_id, provider_id=provider.id,
            billing_type=provider.billing_type.value, tokens_in=anchor_t_in, tokens_out=anchor_t_out,
            cost=anchor_cost, currency=provider.currency,
            detail={"type": "image_gen", "agent": True, "radiate": "anchor_grid"})
        cost_total += anchor_cost

        task_manager.set_checkpoint_state(session_id, {"step": "anchor_grid", "image_url": anchor_url, "cols": cols, "rows": rows})

        grid_images = await _crop_grid(anchor_url, cols, rows)
        if not grid_images or len(grid_images) < n_items:
            logger.warning(f"Grid crop failed: got {len(grid_images or [])} cells, need {n_items}, falling back to direct generation")
            for i in range(n_items):
                item = items[i] if i < len(items) else {}
                item_prompt = item.get("prompt", f"item {i+1}")
                task_manager.update_task(session_id, TaskStatus.GENERATING,
                    progress=i + 1, total=n_items,
                    message=f"直接生成子项 {i + 1}/{n_items}: {item_prompt[:30]}")
                try:
                    if reference_images:
                        response = await client.chat_edit(
                            prompt=f"{item_prompt}. {style_desc} style.",
                            images=reference_images[:4],
                            reference_labels=reference_labels or None,
                        )
                    else:
                        response = await client.generate(
                            prompt=f"{item_prompt}. {style_desc} style.",
                            n=1,
                            size="1024x1024",
                        )
                    urls = ImageClient.extract_images(response)
                    if urls:
                        accumulated_images.extend(urls)
                        steps.append({"type": "tool_result", "name": "generate_image", "content": item_prompt[:200], "args": {"prompt": item_prompt, "count": len(urls)}, "meta": {"image_urls": urls}})
                        item_usage = response.get("usage", {}) if isinstance(response, dict) else {}
                        item_t_in = item_usage.get("prompt_tokens", 0)
                        item_t_out = item_usage.get("completion_tokens", 0)
                        item_cost = calc_cost(provider, tokens_in=item_t_in, tokens_out=item_t_out, call_count=len(urls))
                        await record_billing(db, session_id=session_id, provider_id=provider.id,
                            billing_type=provider.billing_type.value, tokens_in=item_t_in, tokens_out=item_t_out,
                            cost=item_cost, currency=provider.currency,
                            detail={"type": "image_gen", "agent": True, "radiate": "item_fallback", "item_index": i})
                        cost_total += item_cost
                except Exception as e:
                    logger.warning(f"Direct fallback item #{i} failed: {e}")
            task_manager.update_task(session_id, TaskStatus.IDLE)
            return {
                "images": accumulated_images,
                "final_images": accumulated_images,
                "intermediate_images": intermediate_images,
                "steps": steps,
                "strategy": "radiate",
                "cost": cost_total,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cancelled": False,
            }

        for i in range(n_items):
            item = items[i] if i < len(items) else {}
            item_prompt = item.get("prompt", f"item {i+1}")
            task_manager.update_task(session_id, TaskStatus.GENERATING,
                progress=i + 1, total=n_items,
                message=f"生成子项 {i + 1}/{n_items}: {item_prompt[:30]}")

            try:
                edit_images = [grid_images[i]]
                if reference_images:
                    edit_images.extend(reference_images[:3])
                response = await client.chat_edit(
                    prompt=f"{item_prompt}. {style_desc} style.",
                    images=edit_images,
                    reference_labels=reference_labels or None,
                )
                urls = ImageClient.extract_images_from_chat(response)
                if urls:
                    accumulated_images.extend(urls)
                    steps.append({"type": "tool_result", "name": "generate_image", "content": item_prompt[:200], "args": {"prompt": item_prompt, "count": len(urls)}, "meta": {"image_urls": urls}})
                    item_usage = response.get("usage", {}) if isinstance(response, dict) else {}
                    item_t_in = item_usage.get("prompt_tokens", 0)
                    item_t_out = item_usage.get("completion_tokens", 0)
                    item_cost = calc_cost(provider, tokens_in=item_t_in, tokens_out=item_t_out, call_count=len(urls))
                    await record_billing(db, session_id=session_id, provider_id=provider.id,
                        billing_type=provider.billing_type.value, tokens_in=item_t_in, tokens_out=item_t_out,
                        cost=item_cost, currency=provider.currency,
                        detail={"type": "image_gen", "agent": True, "radiate": "item", "item_index": i})
                    cost_total += item_cost
            except Exception as e:
                logger.warning(f"Style anchor item #{i} failed: {e}")

        task_manager.update_task(session_id, TaskStatus.IDLE)
        return {
            "images": accumulated_images,
            "final_images": accumulated_images,
            "intermediate_images": intermediate_images,
            "steps": steps,
            "strategy": "radiate",
            "cost": cost_total,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cancelled": False,
        }

    except Exception as e:
        task_manager.update_task(session_id, TaskStatus.ERROR, message=str(e))
        await add_system_message(db, session_id, f"套图生成失败: {e}", message_type="error")
        return {"error": str(e)}


async def _build_agent_context(db: AsyncSession, session_id: str, max_tokens: int = 3000) -> list[dict]:
    import json
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at.desc()).limit(20)
    )
    msgs = result.scalars().all()
    msgs.reverse()
    context = []
    token_est = 0
    image_count = 0
    for m in reversed(msgs):
        if m.role not in ("user", "assistant"):
            continue
        if m.message_type not in ("text", "agent"):
            continue
        content = m.content or ""
        if m.message_type == "agent" and m.metadata_:
            try:
                meta = json.loads(m.metadata_) if isinstance(m.metadata_, str) else m.metadata_
                content = meta.get("final_output", content)
            except Exception:
                pass
        if not content.strip():
            continue
        est = len(content) // 3
        if token_est + est > max_tokens:
            remain = max_tokens - token_est
            if remain > 0:
                content = content[:remain * 3] + "..."
            else:
                break
        role = m.role.value if hasattr(m.role, "value") else m.role

        image_urls = []
        if m.metadata_ and image_count < 2:
            try:
                meta = json.loads(m.metadata_) if isinstance(m.metadata_, str) else m.metadata_
                image_urls = (meta.get("image_urls") or [])[:2 - image_count]
            except Exception:
                pass

        if image_urls:
            parts: list[dict] = [{"type": "text", "text": f"{content}\n\n[上下文包含 {len(image_urls)} 张已生成的图片]"}]
            context.insert(0, {"role": role, "content": parts})
            image_count += len(image_urls)
        else:
            context.insert(0, {"role": role, "content": content})
        token_est += est
        if token_est >= max_tokens:
            break
    return context


def _extract_items_from_text(text: str) -> list[dict]:
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
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception:
        return None

    client = ImageClient(base_url, api_key, provider.model_id)

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


async def _enhance_with_search(
    db: AsyncSession,
    session_id: str,
    prompt: str,
    task_manager: TaskManager,
) -> str:
    from app.tools.web_search import WebSearchTool
    from app.tools.image_search import ImageSearchTool

    search_provider_result = await db.execute(
        select(ApiProvider).where(
            ApiProvider.provider_type == ProviderType.web_search,
            ApiProvider.is_active == True,
        )
    )
    search_provider = search_provider_result.scalars().first()
    if not search_provider:
        logger.info("No web_search provider configured, skipping search enhancement")
        return ""

    try:
        _, api_key = await resolve_provider_vendor(db, search_provider)
    except Exception as e:
        logger.warning(f"Search API key decryption failed: {e}")
        return ""

    retry_count_val = await get_setting(db, "search_retry_count")
    retry_count = retry_count_val.get("value", 3) if retry_count_val else 3

    task_manager.update_task(session_id, TaskStatus.GENERATING,
        message="搜索参考资料中...")

    search_context_parts = []

    web_tool = WebSearchTool()
    web_result = await web_tool.execute(query=prompt, max_results=5, api_key=api_key, retry_count=retry_count)
    if web_result.content and not web_result.meta.get("error"):
        search_context_parts.append(f"[网页搜索结果]\n{web_result.content}")
        await add_system_message(db, session_id,
            f"搜索参考: 找到相关网页资料",
            message_type="image",
            metadata={"search_type": "web", "sources": web_result.meta.get("sources", [])})

    image_tool = ImageSearchTool()
    img_result = await image_tool.execute(query=prompt, max_results=5, api_key=api_key, retry_count=retry_count)
    if img_result.content and not img_result.meta.get("error"):
        search_context_parts.append(f"[图片搜索结果]\n{img_result.content}")
        image_urls = [s.get("image_url", "") for s in img_result.meta.get("sources", []) if s.get("image_url")]
        if image_urls:
            await add_system_message(db, session_id,
                f"搜索参考: 找到 {len(image_urls)} 张参考图",
                message_type="image",
                metadata={"search_type": "image", "image_urls": image_urls[:4]})

    return "\n\n".join(search_context_parts)


async def handle_agent_generate(db: AsyncSession, data: GenerateRequest) -> dict:
    session_id = data.session_id
    prompt = data.prompt

    task_manager = TaskManager()
    correlation_id = f"agent-{session_id}"

    if not prompt or not prompt.strip():
        task_manager.update_task(session_id, TaskStatus.ERROR, message="提示词不能为空")
        await add_system_message(db, session_id, "提示词不能为空，请输入具体的图像生成需求", message_type="error")
        return {
            "error": "提示词不能为空，请输入具体的图像生成需求",
            "images": [],
            "steps": [],
            "intent": {"task_type": "single", "expected_count": 0, "strategy": "single", "items": [], "references": [], "requires_consistency": False, "user_goal": ""},
        }

    await add_message(db, session_id, MessageCreate(
        content=prompt,
        message_type="text",
        metadata={"agent_mode": True},
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

    # === Resolve LLM provider for hybrid intent parsing ===
    llm_api_key = ""
    llm_base_url = ""
    llm_model_id = ""
    llm_provider_result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
    llm_prov = llm_provider_result.scalar_one_or_none()
    if llm_prov:
        try:
            llm_base_url, llm_api_key = await resolve_provider_vendor(db, llm_prov)
            llm_model_id = llm_prov.model_id
        except Exception as e:
            logger.warning(f"LLM key decrypt failed for intent classifier, falling back to regex: {e}")

    # === Agent Intent Parsing (regex → LLM hybrid) ===
    context_images = _extract_context_image_urls(data.context_messages) or None
    intent = await hybrid_parse_intent(
        prompt=prompt,
        image_count=data.image_count,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model_id=llm_model_id,
        context_images=context_images,
        context_messages=data.context_messages,
        reference_labels=data.reference_labels,
    )
    intent.references = await resolve_context_references(
        db=db,
        session_id=session_id,
        prompt=prompt,
        context_messages=data.context_messages,
        reference_labels=data.reference_labels,
    )
    intent.reference_images = data.reference_images or []
    intent.reference_labels = data.reference_labels or []
    for item in intent.items:
        if not item.reference_urls:
            item.reference_urls = intent.references

    # Strategy is determined by code, not by frontend or LLM
    strategy = STRATEGY_MAP.get(intent.task_type, "single")
    type_label = TASK_TYPE_LABELS.get(intent.task_type, "未知")

    # === Search Enhancement ===
    search_context = ""
    if has_search_intent(prompt):
        search_context = await _enhance_with_search(db, session_id, prompt, task_manager)
        if search_context:
            enhanced_prompt = f"{prompt}\n\n[搜索参考信息]\n{search_context}"
            data.prompt = enhanced_prompt
            prompt = enhanced_prompt

    from app.core.events import LamEvent
    await task_manager.publish(LamEvent(
        event_type="task_started",
        correlation_id=correlation_id,
        payload={
            "type": "task_started",
            "session_id": session_id,
            "task_type": intent.task_type,
            "strategy": strategy,
        },
    ))
    task_manager.update_task(session_id, TaskStatus.GENERATING,
        message=f"{type_label} | 策略: {strategy}",
        task_type=intent.task_type, strategy=strategy)

    # === Fixed Strategy Routing ===
    result: dict | None = None

    if strategy == "single":
        result = await _execute_single(
            db, session_id, data, intent, task_manager,
            image_provider_id, llm_provider_id,
        )

    elif strategy == "parallel":
        result = await execute_multi_independent(
            db=db,
            session_id=session_id,
            intent=intent,
            data=data,
            task_manager=task_manager,
            llm_provider_id=llm_provider_id,
            image_provider_id=image_provider_id,
        )

    elif strategy == "iterative":
        llm_result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
        llm_prov = llm_result.scalar_one_or_none()
        if not llm_prov:
            result = {"error": "LLM provider not found", "images": [], "steps": []}
        else:
            try:
                llm_base_url, llm_api_key = await resolve_provider_vendor(db, llm_prov)
            except Exception as e:
                result = {"error": f"LLM API key decryption failed: {e}", "images": [], "steps": []}
                llm_api_key = ""
                llm_base_url = ""

            if not result:
                task_manager.update_task(session_id, TaskStatus.GENERATING,
                    message=f"迭代精修 | LLM 生成步骤")
                steps = await _generate_iterative_steps(
                    prompt=prompt,
                    llm_api_key=llm_api_key,
                    llm_base_url=llm_base_url,
                    llm_model_id=llm_prov.model_id,
                    context_images=context_images,
                )
                if not steps:
                    result = {"error": "无法生成迭代步骤，请描述更具体（如：先出草图，再精修细节）", "images": [], "steps": []}
                else:
                    result = await execute_iterative(
                        db=db,
                        session_id=session_id,
                        steps=steps,
                        provider_id=image_provider_id,
                        task_manager=task_manager,
                        accumulated_images=[],
                        llm_provider_id=llm_provider_id,
                        reference_images=intent.reference_images or None,
                        reference_labels=intent.reference_labels or None,
                    )

    elif strategy == "radiate":
        llm_result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
        llm_prov = llm_result.scalar_one_or_none()
        if not llm_prov:
            result = {"error": "LLM provider not found", "images": [], "steps": []}
        else:
            try:
                llm_base_url, llm_api_key = await resolve_provider_vendor(db, llm_prov)
            except Exception as e:
                result = {"error": f"LLM API key decryption failed: {e}", "images": [], "steps": []}
                llm_api_key = ""
                llm_base_url = ""

            if not result:
                task_manager.update_task(session_id, TaskStatus.GENERATING,
                    message=f"套图辐射 | LLM 生成子项")
                radiate_params = await _generate_radiate_params(
                    prompt=prompt,
                    expected_count=intent.expected_count,
                    llm_api_key=llm_api_key,
                    llm_base_url=llm_base_url,
                    llm_model_id=llm_prov.model_id,
                    context_images=context_images,
                )
                items = radiate_params.get("items", [])
                if not items:
                    result = {"error": "无法从需求中提取套图子项，请描述更具体（如：做一套6个表情包，包含开心、生气、惊讶...）", "images": [], "steps": []}
                else:
                    plan_meta = {
                        "items": items,
                        "style": radiate_params.get("style", ""),
                        "overall_theme": radiate_params.get("overall_theme", ""),
                    }
                    result = await _execute_radiate(
                        db, session_id, plan_meta, data,
                        task_manager, [], [], [],
                        llm_provider_id, 0, 0, 0.0,
                        reference_images=intent.reference_images or None,
                        reference_labels=intent.reference_labels or None,
                    )

    # === Handle result ===
    if result is None:
        result = {"error": "未知策略，执行失败", "images": [], "steps": []}

    # Handle error results
    if result.get("error"):
        error_msg = result["error"]
        task_manager.update_task(session_id, TaskStatus.ERROR, message=error_msg)
        await add_system_message(db, session_id, f"执行失败: {error_msg}", message_type="error")
        from dataclasses import asdict as _asdict
        intent_data = _asdict(intent)
        await add_system_message(db, session_id,
            f"执行失败: {error_msg}",
            message_type="agent",
            metadata={
                "steps": result.get("steps", []),
                "final_output": f"执行失败: {error_msg}",
                "images": result.get("images", []),
                "final_images": result.get("final_images", []),
                "intermediate_images": [],
                "intent": intent_data,
                "tokens_in": result.get("tokens_in", 0),
                "tokens_out": result.get("tokens_out", 0),
                "cost": result.get("cost", 0),
                "cancelled": False,
                "task_type": intent.task_type,
                "strategy": strategy,
            },
        )
        await task_manager.publish(LamEvent(
            event_type="task_failed",
            correlation_id=correlation_id,
            payload={"type": "agent_error", "session_id": session_id, "error": error_msg},
        ))
        result["intent"] = intent_data
        return result

    # Validate result against intent
    accumulated_images = result.get("images", [])
    if not validate_agent_result(intent, {"images": accumulated_images, "final_images": result.get("final_images", [])}):
        logger.warning(
            f"Agent produced {len(accumulated_images)} images, expected {intent.expected_count}"
        )
        existing_output = result.get("output", "")
        if existing_output.strip():
            result["output"] = existing_output + f"\n\n(注意: 请求 {intent.expected_count} 张，实际生成 {len(accumulated_images)} 张)"
        else:
            result["output"] = f"(注意: 请求 {intent.expected_count} 张，实际生成 {len(accumulated_images)} 张)"

    from dataclasses import asdict as _asdict
    intent_data = _asdict(intent)
    final_output = result.get("output", "Agent 执行完成")
    await add_system_message(db, session_id,
        final_output,
        message_type="agent",
        metadata={
            "steps": result.get("steps", []),
            "final_output": final_output,
            "images": accumulated_images,
            "final_images": result.get("final_images", []),
            "intermediate_images": result.get("intermediate_images", []),
            "intent": intent_data,
            "tokens_in": result.get("tokens_in", 0),
            "tokens_out": result.get("tokens_out", 0),
            "cost": result.get("cost", 0),
            "cancelled": result.get("cancelled", False),
            "task_type": intent.task_type,
            "strategy": strategy,
        },
    )

    task_manager.update_task(session_id, TaskStatus.IDLE)
    await task_manager.publish(LamEvent(
        event_type="task_completed",
        correlation_id=correlation_id,
        payload={
            "type": "agent_done",
            "session_id": session_id,
            "task_type": intent.task_type,
            "strategy": strategy,
            "image_count": len(accumulated_images),
        },
    ))

    result["intent"] = intent_data
    return result


async def _execute_single(
    db: AsyncSession,
    session_id: str,
    data: GenerateRequest,
    intent: AgentIntent,
    task_manager: TaskManager,
    image_provider_id: str,
    llm_provider_id: str,
) -> dict:
    if not image_provider_id:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置图像生成API")
        return {"error": "未配置图像生成API，请先在API管理中添加", "images": [], "steps": []}

    prompt = data.prompt
    image_size = data.image_size or "1024x1024"
    image_count = intent.expected_count

    task_manager.update_task(session_id, TaskStatus.GENERATING,
        message=f"单图生成 | 生成 {image_count} 张图片")

    all_refs: list[str] = list(intent.reference_images or [])
    if intent.references:
        url_b64 = await ImageClient.urls_to_base64(intent.references[:4])
        all_refs.extend(url_b64)
    reference_images = all_refs[:4] if all_refs else None

    try:
        urls, tokens_in, tokens_out = await generate_images_core(
            db=db,
            provider_id=image_provider_id,
            prompt=prompt,
            image_count=image_count,
            image_size=image_size,
            negative_prompt=data.negative_prompt,
            reference_images=reference_images,
            reference_labels=intent.reference_labels or None,
            session_id=session_id,
        )

        if urls:
            pass  # images stored in agent message metadata.images, not as separate message

        if image_provider_id and urls:
            img_provider = await db.execute(select(ApiProvider).where(ApiProvider.id == image_provider_id))
            img_prov = img_provider.scalar_one_or_none()
            if img_prov:
                img_cost = calc_cost(img_prov, tokens_in=tokens_in, tokens_out=tokens_out, call_count=len(urls))
                await record_billing(db, session_id=session_id, provider_id=img_prov.id,
                    billing_type=img_prov.billing_type.value, tokens_in=tokens_in, tokens_out=tokens_out,
                    cost=img_cost, currency=img_prov.currency,
                    detail={"type": "image_gen", "agent": True, "image_count": len(urls)})

        output = f"已生成 {len(urls)} 张图片" if urls else "图像生成API返回空结果，请检查API配置或更换提示词"
        return {
            "output": output,
            "steps": [{"type": "tool_result", "name": "generate_image", "content": prompt[:200], "args": {"prompt": prompt, "count": image_count}, "meta": {"image_urls": urls}}],
            "cost": 0.0,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cancelled": False,
            "images": urls,
            "final_images": [],
            "intermediate_images": [],
        }
    except Exception as e:
        logger.error(f"_execute_single failed: {e}")
        return {"error": f"图片生成失败: {e}", "images": [], "steps": []}
