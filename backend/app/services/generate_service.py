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
from app.schemas.execution import ExecutionPlan, PlanStep
from app.schemas.planning import PlanningContext
from app.schemas.prompt import PromptOptimizeRequest
from app.services.plan_execution_service import PlanExecutionService
from app.services.session_manager import add_message, add_system_message, message_to_response
from app.services.skill_engine import apply_skill, get_skill
from app.services.rule_engine import apply_rules, get_active_rules
from app.services.prompt_optimizer import optimize_prompt
from app.services.settings_service import get_setting
from app.services.task_manager import TaskManager, TaskStatus, task_manager as global_task_manager
from app.services.api_manager import resolve_provider_vendor
from app.utils.image_client import ImageClient, ImageGenError, ImageGenNotSupportedError
from app.utils.llm_client import LLMClient
from app.services.agent_intent_service import (
    AgentIntent,
    STRATEGY_MAP,
    TASK_TYPE_LABELS,
    resolve_context_references,
    validate_agent_result,
)
from app.services.image_context_resolver import ImageContextResolver, SessionImage

logger = logging.getLogger(__name__)


async def handle_generate(db: AsyncSession, data: GenerateRequest) -> dict:
    session_id = data.session_id
    prompt = data.prompt

    task_manager = global_task_manager
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

    skill_plan: ExecutionPlan | None = None
    for skill_id in data.skill_ids:
        skill = await get_skill(db, skill_id)
        if skill:
            result = apply_skill(prompt, skill)
            if isinstance(result, ExecutionPlan):
                skill_plan = result
                break
            else:
                prompt = result

    if skill_plan:
        return await _execute_skill_plan(db, data, skill_plan, prompt, task_manager)

    rules = await get_active_rules(db)
    if rules:
        context = {"prompt": prompt, "negative_prompt": data.negative_prompt}
        result_context = apply_rules(context, rules)
        prompt = result_context.get("prompt", prompt)
        data.negative_prompt = result_context.get("negative_prompt", data.negative_prompt)

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

    llm_provider_id = await _get_default_provider(db, "default_optimize_provider_id")

    if data.refine_mode or data.selected_image_url:
        clarification_result = await _apply_image_context_resolution(
            db=db, data=data, session_id=session_id,
            task_manager=task_manager, correlation_id=f"gen-{session_id}",
        )
        if clarification_result is not None:
            return clarification_result

    context_ref_urls = []
    for msg in (data.context_messages or []):
        for url in (msg.get("image_urls") or []):
            if url.startswith("http"):
                context_ref_urls.append(url)

    plan = ExecutionPlan(
        strategy="single",
        steps=[PlanStep(
            index=0,
            prompt=prompt,
            negative_prompt=data.negative_prompt,
            image_count=data.image_count,
            image_size=data.image_size,
        )],
        plan_meta={"context_reference_urls": context_ref_urls[:4]} if context_ref_urls else {},
        source="generate",
    )

    context = PlanningContext.from_generate_request(
        data,
        image_provider_id=image_provider_id,
        llm_provider_id=llm_provider_id,
    )

    svc = PlanExecutionService()
    trace = await svc.execute(db, plan, context, task_manager)

    all_image_urls = [a.url for st in trace.step_traces for a in st.artifacts if a.url]

    if trace.status == "failed":
        await add_system_message(db, session_id, f"生成失败: {trace.error}", message_type="error")
        return {"error": trace.error, "image_urls": []}

    await add_system_message(db, session_id,
        f"已生成{len(all_image_urls)} 张图片",
        message_type="image",
        metadata={
            "image_urls": all_image_urls,
            "prompt": prompt,
            "negative_prompt": data.negative_prompt,
            "image_size": data.image_size,
            "cost": trace.total_cost,
            "trace": trace.model_dump(),
        },
    )

    task_manager.update_task(session_id, TaskStatus.IDLE)

    return {
        "image_urls": all_image_urls,
        "cost": trace.total_cost,
        "prompt": prompt,
        "trace": trace.model_dump(),
    }


async def _get_default_provider(db: AsyncSession, setting_key: str) -> str | None:
    from app.services.settings_service import get_setting
    result = await get_setting(db, setting_key)
    if result and isinstance(result, dict):
        return result.get("provider_id")
    return None


async def handle_execute_plan(db: AsyncSession, session_id: str, data: "ExecutePlanRequest") -> dict:
    from app.schemas.session import ExecutePlanRequest
    task_manager = TaskManager()
    task_manager.update_task(session_id, TaskStatus.GENERATING, message="规划执行中")

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
            return {"error": "No image provider configured"}
        image_provider_id = provider.id

    llm_provider_id = await _get_default_provider(db, "default_optimize_provider_id")

    plan_steps: list[PlanStep] = []
    for i, s in enumerate(data.steps):
        plan_steps.append(PlanStep(
            index=i,
            prompt=s.prompt,
            negative_prompt=s.negative_prompt,
            description=s.description,
            image_count=s.image_count,
            image_size=s.image_size,
            reference_step_indices=s.reference_step_indices,
            metadata=s.metadata or {},
        ))

    context_ref_urls_wb = []
    for msg in (data.context_messages or []):
        for url in (msg.get("image_urls") or []):
            if url.startswith("http"):
                context_ref_urls_wb.append(url)

    plan = ExecutionPlan(
        strategy=data.strategy,
        steps=plan_steps,
        plan_meta={"context_reference_urls": context_ref_urls_wb[:4]} if context_ref_urls_wb else {},
        source="workbench",
    )

    context = PlanningContext(
        session_id=session_id,
        prompt=data.steps[0].prompt if data.steps else "",
        negative_prompt=data.negative_prompt,
        image_size=data.image_size,
        reference_images=data.reference_images,
        reference_labels=data.reference_labels,
        context_messages=data.context_messages,
        image_provider_id=image_provider_id,
        llm_provider_id=llm_provider_id,
    )

    svc = PlanExecutionService()
    trace = await svc.execute(db, plan, context, task_manager)

    all_urls = [a.url for st in trace.step_traces for a in st.artifacts if a.url]

    if trace.status == "failed":
        task_manager.update_task(session_id, TaskStatus.ERROR, message=trace.error)
        await add_system_message(db, session_id, f"规划执行失败: {trace.error}", message_type="error")
        return {"error": trace.error, "image_urls": [], "steps": []}

    await add_system_message(db, session_id,
        f"规划执行完成: 已生成 {len(all_urls)} 张图片",
        message_type="image",
        metadata={
            "image_urls": all_urls,
            "plan_strategy": data.strategy,
            "cost": trace.total_cost,
            "step_traces": [st.model_dump() for st in trace.step_traces],
        },
    )

    task_manager.update_task(session_id, TaskStatus.IDLE)

    return {
        "image_urls": all_urls,
        "cost": trace.total_cost,
        "plan_strategy": data.strategy,
        "steps": [st.model_dump() for st in trace.step_traces],
        "trace": trace.model_dump(),
    }


async def _execute_skill_plan(
    db: AsyncSession,
    data: GenerateRequest,
    plan: ExecutionPlan,
    original_prompt: str,
    task_manager: TaskManager,
) -> dict:
    session_id = data.session_id
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
            return {"error": "No image provider configured"}
        image_provider_id = provider.id

    llm_provider_id = await _get_default_provider(db, "default_optimize_provider_id")

    context = PlanningContext.from_generate_request(
        data,
        image_provider_id=image_provider_id,
        llm_provider_id=llm_provider_id,
    )

    svc = PlanExecutionService()
    trace = await svc.execute(db, plan, context, task_manager)

    all_urls = [a.url for st in trace.step_traces for a in st.artifacts if a.url]

    if trace.status == "failed":
        await add_system_message(db, session_id, f"Skill 执行失败: {trace.error}", message_type="error")
        return {"error": trace.error, "image_urls": [], "steps": []}

    await add_system_message(db, session_id,
        f"已生成 {len(all_urls)} 张图片 (skill: {plan.plan_meta.get('skill_name', '')})",
        message_type="image",
        metadata={
            "image_urls": all_urls,
            "prompt": original_prompt,
            "plan_strategy": plan.strategy,
            "cost": trace.total_cost,
        },
    )

    task_manager.update_task(session_id, TaskStatus.IDLE)

    return {
        "image_urls": all_urls,
        "cost": trace.total_cost,
        "prompt": original_prompt,
        "plan_strategy": plan.strategy,
        "trace": trace.model_dump(),
    }


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
    logger.info(
        f"generate_images_core: start, provider_id={provider_id}, "
        f"image_count={image_count}, image_size={image_size}, "
        f"reference_images={len(reference_images) if reference_images else 0}"
    )

    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError(f"Image provider not found: {provider_id}")

    base_url, api_key = await resolve_provider_vendor(db, provider)
    client = ImageClient(base_url, api_key, provider.model_id)

    logger.info(f"generate_images_core: provider resolved, model_id={provider.model_id}")

    all_image_urls: list[str] = []
    tokens_in = 0
    tokens_out = 0

    if reference_images:
        logger.info(f"generate_images_core: reference images detected, trying Tier 1 (chat_edit)")
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
                logger.info(f"generate_images_core: Tier 1 (chat_edit) success, got {len(urls)} images")
                remaining = image_count - len(urls)
                if remaining > 0:
                    logger.info(f"generate_images_core: generating {remaining} more images via chat_edit")
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
            logger.info(f"generate_images_core: Tier 1 (chat_edit) not supported, falling through")
        except ImageGenError as e:
            logger.warning(f"Chat edit failed: {e}")

        if not all_image_urls:
            logger.info(f"generate_images_core: trying Tier 2 (native edit)")
            try:
                response = await client.edit(prompt=prompt, images=reference_images, n=1, size=image_size)
                urls = ImageClient.extract_images(response)
                all_image_urls.extend(urls)
                if urls:
                    logger.info(f"generate_images_core: Tier 2 (native edit) success, got {len(urls)} images")
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
            logger.info(f"generate_images_core: trying Tier 3 (vision fallback + generate)")
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
            if all_image_urls:
                logger.info(f"generate_images_core: Tier 3 (vision fallback) success, got {len(all_image_urls)} images")
    else:
        logger.info(f"generate_images_core: no reference images, using pure text generation")
        try:
            r = await client.generate(prompt=prompt, negative_prompt=negative_prompt, n=image_count, size=image_size)
            urls = ImageClient.extract_images(r)
            all_image_urls.extend(urls)
            logger.info(f"generate_images_core: pure text generation success, got {len(urls)} images")
        except Exception as e:
            logger.error(f"Pure text generation failed: {e}")

    logger.info(f"generate_images_core: completed, total_images={len(all_image_urls)}, tokens_in={tokens_in}, tokens_out={tokens_out}")
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
    for m in msgs:
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
            parts: list[dict] = [{"type": "text", "text": content}]
            for img_url in image_urls:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": img_url, "detail": "auto"},
                })
            context.insert(0, {"role": role, "content": parts})
            image_count += len(image_urls)
        else:
            context.insert(0, {"role": role, "content": content})
        token_est += est
        if token_est >= max_tokens:
            break
    return context


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

    logger.info(f"=== handle_agent_generate START === session_id={session_id}, prompt={prompt[:100]}...")

    task_manager = TaskManager()
    correlation_id = f"agent-{session_id}"

    if not prompt or not prompt.strip():
        logger.warning(f"handle_agent_generate: empty prompt, session_id={session_id}")
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
        logger.error(f"handle_agent_generate: no LLM provider configured, session_id={session_id}")
        task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置LLM")
        await add_system_message(db, session_id, "未配置LLM，请先在API管理中添加", message_type="error")
        return {"error": "No LLM provider configured"}

    logger.info(f"handle_agent_generate: llm_provider_id={llm_provider_id}")

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

    logger.info(f"handle_agent_generate: image_provider_id={image_provider_id}")

    context_images = _extract_context_image_urls_from_messages(data.context_messages)
    logger.info(f"handle_agent_generate: context_images count={len(context_images) if context_images else 0}")

    clarification_result = await _apply_image_context_resolution(
        db=db, data=data, session_id=session_id,
        task_manager=task_manager, correlation_id=correlation_id,
    )
    if clarification_result is not None:
        return clarification_result

    forced_strategy = data.agent_plan_strategy if data.agent_plan_strategy else ""
    if forced_strategy:
        from app.services.agent_intent_service import STRATEGY_MAP
        task_type_for_strategy = next((k for k, v in STRATEGY_MAP.items() if v == forced_strategy), forced_strategy)
        skeleton_intent = {
            "task_type": task_type_for_strategy,
            "expected_count": data.image_count,
            "strategy": forced_strategy,
            "items": [],
            "references": [],
            "confidence": 1.0,
            "needs_search": False,
            "user_goal": prompt,
            "reason": f"forced by agent_plan_strategy={forced_strategy}",
        }
    else:
        skeleton_intent = {
            "task_type": "single",
            "expected_count": data.image_count,
            "strategy": "single",
            "items": [],
            "references": [],
            "confidence": 0.0,
            "needs_search": False,
            "user_goal": prompt,
        }

    context_refs = await resolve_context_references(
        db=db,
        session_id=session_id,
        prompt=prompt,
        context_messages=data.context_messages,
        reference_labels=data.reference_labels,
    )

    from app.core.events import LamEvent
    await task_manager.publish(LamEvent(
        event_type="task_started",
        correlation_id=correlation_id,
        payload={
            "type": "task_started",
            "session_id": session_id,
        },
    ))
    task_manager.update_task(session_id, TaskStatus.GENERATING,
        message="智能生成 | 策略由 Graph 决定")

    result = await _run_agent_mode_graph(
        db=db,
        session_id=session_id,
        prompt=prompt,
        data=data,
        intent_data=skeleton_intent,
        image_provider_id=image_provider_id,
        llm_provider_id=llm_provider_id,
        context_images=context_images,
        context_refs=context_refs,
        correlation_id=correlation_id,
        task_manager=task_manager,
    )

    if result is None:
        logger.warning(f"handle_agent_generate: graph failed, falling back to direct execution")
        result = await _execute_direct(
            db=db,
            session_id=session_id,
            data=data,
            image_provider_id=image_provider_id,
            task_manager=task_manager,
            correlation_id=correlation_id,
            intent_data=skeleton_intent,
        )

    logger.info(f"=== handle_agent_generate END === session_id={session_id}")
    return result


async def _run_agent_mode_graph(
    db: AsyncSession,
    session_id: str,
    prompt: str,
    data: GenerateRequest,
    intent_data: dict,
    image_provider_id: str | None,
    llm_provider_id: str | None,
    context_images: list[str] | None,
    context_refs: list[str],
    correlation_id: str,
    task_manager: TaskManager,
) -> dict | None:
    import uuid
    from app.core.agent.graph import build_agent_mode_graph
    from app.core.agent.state import AgentState
    from app.core.events import LamEvent
    from langgraph.types import Command

    try:
        graph = build_agent_mode_graph()
    except Exception as e:
        logger.warning(f"_run_agent_mode_graph: failed to build graph: {e}, falling back")
        return None

    initial_state: dict = {
        "session_id": session_id,
        "prompt": prompt,
        "negative_prompt": data.negative_prompt,
        "image_count": data.image_count,
        "image_size": data.image_size,
        "reference_images": data.reference_images or [],
        "reference_labels": data.reference_labels or [],
        "context_images": context_images or [],
        "context_reference_urls": context_refs,
        "search_context": "",
        "needs_search": False,
        "skill_ids": data.skill_ids,
        "image_provider_id": image_provider_id or "",
        "llm_provider_id": llm_provider_id or "",
        "intent": intent_data,
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "cost": 0.0,
        "rounds": 0,
        "retry_count": 0,
        "retry_step_index": -1,
        "status": "running",
    }

    thread_id = f"agent-{session_id}-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {
            "thread_id": thread_id,
            "db": db,
            "task_manager": task_manager,
        },
        "recursion_limit": 50,
    }

    max_loops = 12
    loop_count = 0
    current_state = initial_state

    while loop_count < max_loops:
        loop_count += 1

        # Check for external cancellation
        if task_manager.get_cancel_event(session_id).is_set():
            logger.info(f"_run_agent_mode_graph: cancelled externally, loop={loop_count}")
            result = {"error": "已取消", "images": [], "steps": [], "intent": intent_data, "cancelled": True}
            await add_system_message(db, session_id, "任务已取消", message_type="agent",
                metadata={"cancelled": True, "intent": intent_data})
            task_manager.update_task(session_id, TaskStatus.IDLE)
            await task_manager.publish(LamEvent(
                event_type="task_completed",
                correlation_id=correlation_id,
                payload={"type": "agent_cancelled", "session_id": session_id},
            ))
            return result

        try:
            if loop_count == 1:
                result_state = await graph.ainvoke(current_state, config)
            else:
                resume_action = task_manager.get_checkpoint_state(session_id)
                action = resume_action.get("retry_level", "approve") if resume_action else "approve"
                result_state = await graph.ainvoke(Command(resume=action), config)
        except Exception as e:
            logger.error(f"_run_agent_mode_graph: graph execution failed: {e}")
            task_manager.update_task(session_id, TaskStatus.ERROR, message=f"Graph 执行失败: {e}")
            await add_system_message(db, session_id, f"执行失败: {e}", message_type="error")
            await task_manager.publish(LamEvent(
                event_type="task_failed",
                correlation_id=correlation_id,
                payload={"type": "agent_error", "session_id": session_id, "error": str(e)},
            ))
            from dataclasses import asdict as _asdict
            return {"error": str(e), "images": [], "steps": [], "intent": intent_data}

        status = result_state.get("status", "")
        logger.info(f"_run_agent_mode_graph: loop={loop_count} status={status} intent_conf={result_state.get('intent', {}).get('confidence', 'N/A')}")

        if status == "executed" or status == "completed":
            logger.info(f"_run_agent_mode_graph: completed, artifacts={len(result_state.get('artifacts', []))}")
            break

        if status in ("error", "cancelled"):
            logger.error(f"_run_agent_mode_graph: graph ended with status={status}")
            break

        if status == "replan_needed":
            logger.info(f"_run_agent_mode_graph: replan triggered, continuing")
            current_state = result_state
            continue

        # === Graph interrupted by checkpoint ===
        logger.info(f"_run_agent_mode_graph: checkpoint interrupt detected, thread_id={thread_id}")
        task_manager.store_graph_config(session_id, config)

        # Set up checkpoint wait event
        task_manager.set_checkpoint_state(session_id, {
            "event": result_state,
            "event_obj": asyncio.Event(),
            "created_at": __import__("time").time(),
            "approved": False,
            "retry_level": "approve",
            "graph_config": config,
        })

        # Wait for user action at checkpoint
        resolved = await task_manager.wait_checkpoint(session_id, timeout=300.0)
        if not resolved:
            logger.warning(f"_run_agent_mode_graph: checkpoint rejected/timeout for {session_id}")
            task_manager.update_task(session_id, TaskStatus.ERROR, message="Checkpoint 被拒绝或超时")
            await task_manager.publish(LamEvent(
                event_type="task_failed",
                correlation_id=correlation_id,
                payload={"type": "agent_error", "session_id": session_id, "error": "Checkpoint 被拒绝或超时"},
            ))
            return {
                "error": "checkpoint rejected",
                "images": [],
                "steps": [],
                "intent": intent_data,
            }

        current_state = result_state
        # Loop back to resume the graph with Command(resume=action)

    if loop_count >= max_loops:
        logger.error(f"_run_agent_mode_graph: exceeded max_loops ({max_loops})")
        task_manager.update_task(session_id, TaskStatus.ERROR, message="执行循环超限")
        await task_manager.publish(LamEvent(
            event_type="task_failed",
            correlation_id=correlation_id,
            payload={"type": "agent_error", "session_id": session_id, "error": "执行循环超限"},
        ))
        return {"error": "执行循环超限", "images": [], "steps": [], "intent": intent_data}

    if result_state is None:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="执行失败")
        await task_manager.publish(LamEvent(
            event_type="task_failed",
            correlation_id=correlation_id,
            payload={"type": "agent_error", "session_id": session_id, "error": "执行失败"},
        ))
        return {"error": "执行失败", "images": [], "steps": [], "intent": intent_data}

    status = result_state.get("status", "")
    if status == "cancelled":
        task_manager.update_task(session_id, TaskStatus.IDLE)
        await add_system_message(db, session_id, "任务已取消", message_type="agent",
            metadata={"cancelled": True, "intent": intent_data})
        await task_manager.publish(LamEvent(
            event_type="task_completed",
            correlation_id=correlation_id,
            payload={"type": "agent_cancelled", "session_id": session_id},
        ))
        return {"error": "已取消", "images": [], "steps": [], "intent": intent_data, "cancelled": True}

    if status == "error":
        task_manager.update_task(session_id, TaskStatus.ERROR, message=result_state.get("error", "执行失败"))
        await task_manager.publish(LamEvent(
            event_type="task_failed",
            correlation_id=correlation_id,
            payload={"type": "agent_error", "session_id": session_id, "error": result_state.get("error", "执行失败")},
        ))
        return {"error": result_state.get("error", "执行失败"), "images": [], "steps": [], "intent": intent_data}

    # Post-process graph result → frontend-compatible format
    artifacts: list[dict] = result_state.get("artifacts", [])
    all_urls = [a.get("url", "") for a in artifacts if a.get("url")]
    cost = result_state.get("cost", 0.0)
    tokens_in = result_state.get("total_tokens_in", 0)
    tokens_out = result_state.get("total_tokens_out", 0)

    if not validate_agent_result(AgentIntent(**intent_data), {"images": all_urls, "final_images": all_urls}):
        logger.warning(f"Agent graph produced {len(all_urls)} images, expected {intent_data.get('expected_count', 1)}")

    final_output = f"已生成 {len(all_urls)} 张图片"
    step_traces_raw = result_state.get("step_traces", [])

    task_type = result_state.get("intent", {}).get("task_type", "single")
    strategy = result_state.get("intent", {}).get("strategy", "single")

    execution_plan = result_state.get("execution_plan", {})
    critic_results = result_state.get("critic_results", [])
    decision_result = result_state.get("decision_result", "")
    planning_ctx = result_state.get("planning_context", {})
    image_descriptions = planning_ctx.get("image_descriptions", {}) if isinstance(planning_ctx, dict) else {}

    node_trace = []
    for key in ("intent", "skill_matcher", "skill", "context_enrichment", "planner", "prompt_builder", "executor", "critic", "decision"):
        node_status = result_state.get("status", "")
        if key == "intent" and result_state.get("intent"):
            node_trace.append({"node": "intent", "status": "done", "task_type": task_type})
        elif key == "planner" and execution_plan:
            node_trace.append({"node": "planner", "status": "done", "strategy": execution_plan.get("strategy", ""), "steps": len(execution_plan.get("steps", []))})
        elif key == "critic" and critic_results:
            avg = sum(r.get("score", 0) for r in critic_results) / len(critic_results) if critic_results else 0
            node_trace.append({"node": "critic", "status": "done", "avg_score": round(avg, 1), "artifacts_reviewed": len(critic_results)})
        elif key == "decision" and decision_result:
            node_trace.append({"node": "decision", "status": "done", "result": decision_result, "retry_count": result_state.get("retry_count", 0)})

    await add_system_message(db, session_id,
        final_output,
        message_type="agent",
        metadata={
            "steps": step_traces_raw,
            "final_output": final_output,
            "images": all_urls,
            "final_images": all_urls,
            "intermediate_images": [],
            "intent": result_state.get("intent", intent_data),
            "plan": {
                "strategy": execution_plan.get("strategy", strategy),
                "steps": [{"index": s.get("index", i), "prompt": s.get("prompt", ""), "description": s.get("description", "")} for i, s in enumerate(execution_plan.get("steps", []))],
                "source": execution_plan.get("source", ""),
            } if execution_plan else None,
            "critic": {
                "results": [{"artifact_id": r.get("artifact_id", "")[:60], "score": r.get("score", 0), "issues": r.get("issues", [])} for r in critic_results],
                "avg_score": round(sum(r.get("score", 0) for r in critic_results) / len(critic_results), 1) if critic_results else None,
            } if critic_results else None,
            "decision": decision_result or None,
            "node_trace": node_trace,
            "image_descriptions": image_descriptions,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": cost,
            "cancelled": False,
            "task_type": task_type,
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
            "task_type": task_type,
            "strategy": strategy,
            "image_count": len(all_urls),
        },
    ))

    raw_intent = result_state.get("intent") or {}
    return_intent = raw_intent if raw_intent.get("confidence", 0) > 0 else intent_data

    return {
        "output": final_output,
        "steps": step_traces_raw,
        "cost": cost,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cancelled": False,
        "images": all_urls,
        "final_images": all_urls,
        "intermediate_images": [],
        "intent": return_intent,
    }


async def _execute_direct(
    db: AsyncSession,
    session_id: str,
    data: GenerateRequest,
    image_provider_id: str | None,
    task_manager: TaskManager,
    correlation_id: str,
    intent_data: dict,
) -> dict:
    from app.core.events import LamEvent

    logger.warning(f"_execute_direct: graph failed, falling back to direct generation for session_id={session_id}")

    if not image_provider_id:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置图像生成API")
        await add_system_message(db, session_id, "未配置图像生成API", message_type="error")
        await task_manager.publish(LamEvent(
            event_type="task_failed",
            correlation_id=correlation_id,
            payload={"type": "agent_error", "session_id": session_id, "error": "未配置图像生成API"},
        ))
        return {"error": "未配置图像生成API", "images": [], "steps": [], "intent": intent_data}

    try:
        urls, tokens_in, tokens_out = await generate_images_core(
            db=db,
            provider_id=image_provider_id,
            prompt=data.prompt,
            image_count=data.image_count,
            image_size=data.image_size,
            negative_prompt=data.negative_prompt,
            reference_images=data.reference_images or None,
            reference_labels=data.reference_labels or None,
            session_id=session_id,
        )

        if image_provider_id and urls:
            img_provider = await db.execute(select(ApiProvider).where(ApiProvider.id == image_provider_id))
            img_prov = img_provider.scalar_one_or_none()
            if img_prov:
                img_cost = calc_cost(img_prov, tokens_in=tokens_in, tokens_out=tokens_out, call_count=len(urls))
                await record_billing(db, session_id=session_id, provider_id=img_prov.id,
                    billing_type=img_prov.billing_type.value, tokens_in=tokens_in, tokens_out=tokens_out,
                    cost=img_cost, currency=img_prov.currency,
                    detail={"type": "image_gen", "agent": True, "image_count": len(urls)})

        final_output = f"已生成 {len(urls)} 张图片" if urls else "图像生成API返回空结果"
        await add_system_message(db, session_id,
            final_output,
            message_type="agent",
            metadata={
                "final_output": final_output,
                "images": urls,
                "final_images": urls,
        "intent": result_state.get("intent", intent_data),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost": 0.0,
                "cancelled": False,
                "task_type": "single",
                "strategy": "single",
            },
        )

        task_manager.update_task(session_id, TaskStatus.IDLE)
        await task_manager.publish(LamEvent(
            event_type="task_completed",
            correlation_id=correlation_id,
            payload={"type": "agent_done", "session_id": session_id, "task_type": "single", "strategy": "single", "image_count": len(urls)},
        ))

        return {
            "output": final_output,
            "cost": 0.0,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cancelled": False,
            "images": urls,
            "final_images": urls,
            "intermediate_images": [],
            "intent": intent_data,
        }
    except Exception as e:
        logger.error(f"_execute_direct failed: {e}")
        task_manager.update_task(session_id, TaskStatus.ERROR, message=str(e))
        await task_manager.publish(LamEvent(
            event_type="task_failed",
            correlation_id=correlation_id,
            payload={"type": "agent_error", "session_id": session_id, "error": str(e)},
        ))
        return {"error": str(e), "images": [], "steps": [], "intent": intent_data}


def _extract_context_image_urls_from_messages(messages: list[dict] | None) -> list[str]:
    if not messages:
        return []
    urls: list[str] = []
    for msg in messages:
        for url in (msg.get("image_urls") or []):
            if url.startswith("http"):
                urls.append(url)
    return urls


async def _build_session_images(db: AsyncSession, session_id: str) -> list[SessionImage]:
    from sqlalchemy import select, or_
    from app.models.message import Message, MessageRole, MessageType

    result = await db.execute(
        select(Message)
        .where(
            Message.session_id == session_id,
            Message.role == MessageRole.assistant,
            or_(
                Message.message_type == MessageType.image,
                Message.message_type == "agent",
            ),
        )
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    messages = result.scalars().all()

    images: list[SessionImage] = []
    for msg_idx, msg in enumerate(messages):
        meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
        if msg.message_type == "agent":
            img_urls = meta.get("images", [])
        else:
            img_urls = meta.get("image_urls", [])
        for url in img_urls:
            if isinstance(url, str) and url.startswith("http"):
                images.append(SessionImage(
                    url=url,
                    message_id=str(msg.id),
                    message_index=msg_idx,
                    is_from_latest=(msg_idx == 0),
                ))
    return images


async def _apply_image_context_resolution(
    db: AsyncSession,
    data: GenerateRequest,
    session_id: str,
    task_manager: TaskManager,
    correlation_id: str,
) -> dict | None:
    session_images = await _build_session_images(db, session_id)

    manual_refine: list[str] = []
    if data.refine_mode and data.reference_images:
        manual_refine = [img for img in data.reference_images if img.startswith("data:")]

    resolver = ImageContextResolver()
    resolution = resolver.resolve_image_context(
        prompt=data.prompt,
        session_images=session_images,
        manual_refine_images=manual_refine,
        selected_image_url=data.selected_image_url,
        refine_mode=data.refine_mode,
    )

    logger.info(
        f"ImageContextResolver: mode={resolution.mode}, "
        f"targets={len(resolution.target_images)}, "
        f"refs={len(resolution.reference_images)}, "
        f"confidence={resolution.confidence}, "
        f"reason={resolution.reason}"
    )

    if resolution.mode == "ask_clarification":
        from app.core.events import LamEvent
        await task_manager.publish(LamEvent(
            event_type="task_completed",
            correlation_id=correlation_id,
            payload={
                "type": "agent_done",
                "session_id": session_id,
                "clarification": resolution.clarification,
            },
        ))
        await add_system_message(db, session_id, resolution.clarification, message_type="agent",
            metadata={"clarification": True})
        task_manager.update_task(session_id, TaskStatus.IDLE)
        return {"clarification": resolution.clarification}

    urls_to_convert: list[str] = []
    if resolution.mode == "edit_target":
        urls_to_convert = resolution.target_images[:1]
    elif resolution.mode == "batch_edit":
        urls_to_convert = resolution.target_images[:4]
    elif resolution.mode == "style_reference":
        urls_to_convert = resolution.reference_images[:2]

    if urls_to_convert:
        try:
            b64_images = await ImageClient.urls_to_base64(urls_to_convert)
            existing_refs = list(data.reference_images or [])
            existing_refs.extend(b64_images)
            data.reference_images = existing_refs

            new_labels: list[dict] = []
            offset = len(data.reference_labels or [])
            for i, url in enumerate(urls_to_convert):
                new_labels.append({
                    "index": offset + i + 1,
                    "source": "auto_context",
                    "name": f"图{offset + i + 1}",
                    "label": f"图{offset + i + 1}",
                    "url": url,
                })
            existing_labels = list(data.reference_labels or [])
            existing_labels.extend(new_labels)
            data.reference_labels = existing_labels

            logger.info(f"ImageContextResolver: added {len(b64_images)} auto-context images to reference_images")
        except Exception as e:
            logger.warning(f"ImageContextResolver: failed to convert URLs to base64: {e}")

    return None
