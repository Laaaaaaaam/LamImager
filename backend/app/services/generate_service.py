from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider, ProviderType
from app.models.billing import BillingRecord, BillingRecordType
from app.schemas.session import GenerateRequest
from app.schemas.prompt import PromptOptimizeRequest
from app.services.session_manager import add_message, add_system_message, message_to_response
from app.services.skill_engine import apply_skill, get_skill
from app.services.rule_engine import apply_rules, get_active_rules
from app.services.prompt_optimizer import optimize_prompt
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

    from app.schemas.session import MessageCreate
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

    if data.context_messages:
        context_parts = []
        for msg in data.context_messages[-10:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                context_parts.append(f"[User]: {content}")
            elif role == "assistant":
                context_parts.append(f"[Assistant]: {content}")
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

    api_key = decrypt(provider.api_key_enc)
    client = ImageClient(provider.base_url, api_key, provider.model_id)

    try:
        all_image_urls = []
        semaphore = asyncio.Semaphore(5)
        task_manager.update_task(session_id, TaskStatus.GENERATING, progress=0, total=data.image_count, message=f"生成中 0/{data.image_count}")

        if data.reference_images:
            result = await _generate_with_references(
                db, session_id, client, provider, prompt, data, all_image_urls, semaphore
            )
            if result:
                return result
        else:
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

        cost = _compute_cost(provider, data.image_count)

        billing = BillingRecord(
            session_id=session_id,
            provider_id=provider.id,
            billing_type=BillingRecordType(provider.billing_type.value),
            cost=cost,
            currency=provider.currency,
            detail={"prompt": prompt, "image_count": data.image_count, "image_size": data.image_size},
        )
        db.add(billing)
        await db.commit()

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


async def _describe_reference_images(db: AsyncSession, provider_id: str, reference_images: list[str]) -> str:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError("LLM provider not found")

    api_key = decrypt(provider.api_key_enc)
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

    cost = 0.0
    if provider.billing_type.value == "per_token" and provider.unit_price:
        cost = float(provider.unit_price) * (tokens_in + tokens_out) / 1000

    billing = BillingRecord(
        provider_id=provider.id,
        billing_type=BillingRecordType.per_token,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        currency=provider.currency,
        detail={"type": "image_description", "image_count": len(reference_images)},
    )
    db.add(billing)
    await db.commit()

    return description


def _compute_cost(provider: ApiProvider, image_count: int) -> float:
    if provider.billing_type.value == "per_call":
        return float(provider.unit_price) * image_count
    elif provider.billing_type.value == "per_token":
        return float(provider.unit_price)
    return 0.0


async def _generate_with_references(
    db: AsyncSession,
    session_id: str,
    client: ImageClient,
    provider: ApiProvider,
    prompt: str,
    data: GenerateRequest,
    all_image_urls: list[str],
    semaphore: asyncio.Semaphore,
) -> dict | None:
    try:
        response = await client.chat_edit(
            prompt=prompt,
            images=data.reference_images,
        )
        urls = ImageClient.extract_images_from_chat(response)
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
                            )
                            return ImageClient.extract_images_from_chat(response)
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
            image_desc = await _describe_reference_images(db, llm_provider_id, reference_images)
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
