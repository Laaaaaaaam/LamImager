from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.billing_service import calc_cost, record_billing
from app.services.session_manager import add_system_message
from app.services.settings_service import get_setting
from app.services.task_manager import TaskManager, TaskStatus

logger = logging.getLogger(__name__)


async def execute_parallel(
    db: AsyncSession,
    session_id: str,
    steps: list[dict],
    provider_id: str,
    task_manager: TaskManager,
    accumulated_images: list[str],
    llm_provider_id: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_total: float = 0.0,
) -> dict | None:
    if not steps:
        logger.warning("execute_parallel: no steps to execute")
        task_manager.update_task(session_id, TaskStatus.ERROR, message="没有可执行的步骤")
        return {"error": "没有可执行的步骤", "images": [], "steps": []}
    if not provider_id:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置图像生成API")
        return {"error": "No image provider"}

    concurrent_val = await get_setting(db, "max_concurrent")
    max_concurrent = concurrent_val.get("value", 5) if concurrent_val else 5
    semaphore = asyncio.Semaphore(max_concurrent)
    task_manager.update_task(session_id, TaskStatus.GENERATING, message=f"并发执行 {len(steps)} 个步骤")

    from app.models.api_provider import ApiProvider
    from sqlalchemy import select
    from app.services.generate_service import generate_images_core

    provider_result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    img_prov = provider_result.scalar_one_or_none()

    async def _run_step(idx: int, step: dict) -> dict:
        async with semaphore:
            prompt = step.get("prompt", "")
            if not prompt:
                return {"step_index": idx, "images": [], "tokens_in": 0, "tokens_out": 0, "error": "empty prompt"}
            neg_prompt = step.get("negative_prompt", "")
            image_count = step.get("image_count", 1)
            image_size = step.get("image_size", "")
            desc = step.get("description", "") or prompt[:60]
            try:
                task_manager.update_task(session_id, TaskStatus.GENERATING,
                    progress=idx + 1, total=len(steps),
                    message=f"步骤 {idx + 1}/{len(steps)}: {desc[:40]}")
                urls, t_in, t_out = await generate_images_core(
                    db=db,
                    provider_id=provider_id,
                    prompt=prompt,
                    image_count=image_count,
                    image_size=image_size or "1024x1024",
                    negative_prompt=neg_prompt,
                    session_id=session_id,
                )
                if urls:
                    await add_system_message(db, session_id,
                        f"步骤 {idx + 1}: {desc}",
                        message_type="image",
                        metadata={"image_urls": urls, "step_index": idx, "step_description": desc},
                    )
                    if img_prov:
                        step_cost = calc_cost(img_prov, tokens_in=t_in, tokens_out=t_out, call_count=len(urls))
                        await record_billing(db, session_id=session_id, provider_id=img_prov.id,
                            billing_type=img_prov.billing_type.value, tokens_in=t_in, tokens_out=t_out,
                            cost=step_cost, currency=img_prov.currency,
                            detail={"type": "image_gen", "plan": "parallel", "step_index": idx, "image_count": len(urls)})
                return {"step_index": idx, "images": urls, "tokens_in": t_in, "tokens_out": t_out}
            except Exception as e:
                logger.error(f"Parallel step {idx} failed: {e}")
                return {"step_index": idx, "images": [], "tokens_in": 0, "tokens_out": 0, "error": str(e)}

    tasks = [_run_step(i, s) for i, s in enumerate(steps)]
    results = await asyncio.gather(*tasks)

    total_t_in = tokens_in
    total_t_out = tokens_out
    total_cost = cost_total
    all_images = list(accumulated_images)

    for r in sorted(results, key=lambda x: x.get("step_index", 0)):
        imgs = r.get("images", [])
        all_images.extend(imgs)
        total_t_in += r.get("tokens_in", 0)
        total_t_out += r.get("tokens_out", 0)

    task_manager.update_task(session_id, TaskStatus.IDLE)
    return {
        "images": all_images,
        "steps": results,
        "strategy": "parallel",
        "tokens_in": total_t_in,
        "tokens_out": total_t_out,
        "cost": total_cost,
        "cancelled": False,
    }


async def execute_iterative(
    db: AsyncSession,
    session_id: str,
    steps: list[dict],
    provider_id: str,
    task_manager: TaskManager,
    accumulated_images: list[str],
    llm_provider_id: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_total: float = 0.0,
    reference_images: list[str] | None = None,
    reference_labels: list[dict] | None = None,
) -> dict | None:
    logger.info(f"execute_iterative: start, session_id={session_id}, steps={len(steps)}")

    if not steps:
        logger.warning("execute_iterative: no steps to execute")
        task_manager.update_task(session_id, TaskStatus.ERROR, message="没有可执行的步骤")
        return {"error": "没有可执行的步骤", "images": [], "steps": []}
    if not provider_id:
        logger.error(f"execute_iterative: no image provider configured")
        task_manager.update_task(session_id, TaskStatus.ERROR, message="未配置图像生成API")
        return {"error": "No image provider"}

    from app.models.api_provider import ApiProvider
    from sqlalchemy import select
    from app.services.generate_service import generate_images_core

    provider_result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    img_prov = provider_result.scalar_one_or_none()

    all_images = list(accumulated_images)
    step_results = []
    ref_images = reference_images or None
    total_t_in = tokens_in
    total_t_out = tokens_out
    total_cost = cost_total

    for idx, step in enumerate(steps):
        prompt = step.get("prompt", "")
        if not prompt:
            logger.warning(f"execute_iterative: step {idx} has empty prompt")
            step_results.append({"step_index": idx, "images": [], "tokens_in": 0, "tokens_out": 0, "error": "empty prompt"})
            continue
        neg_prompt = step.get("negative_prompt", "")
        image_count = step.get("image_count", 1)
        image_size = step.get("image_size", "")
        desc = step.get("description", "") or prompt[:60]

        logger.info(f"execute_iterative: step {idx+1}/{len(steps)}, desc={desc[:40]}")

        try:
            task_manager.update_task(session_id, TaskStatus.GENERATING,
                progress=idx + 1, total=len(steps),
                message=f"步骤 {idx + 1}/{len(steps)}: {desc[:40]}")
            urls, t_in, t_out = await generate_images_core(
                db=db,
                provider_id=provider_id,
                prompt=prompt,
                image_count=image_count,
                image_size=image_size or "1024x1024",
                reference_images=ref_images,
                reference_labels=reference_labels or None,
                negative_prompt=neg_prompt,
                session_id=session_id,
            )
            if urls:
                ref_images = urls[:1]
                all_images.extend(urls)
                logger.info(f"execute_iterative: step {idx+1} success, got {len(urls)} images")
                await add_system_message(db, session_id,
                    f"步骤 {idx + 1}: {desc}",
                    message_type="image",
                    metadata={"image_urls": urls, "step_index": idx, "step_description": desc},
                )
                if img_prov:
                    step_cost = calc_cost(img_prov, tokens_in=t_in, tokens_out=t_out, call_count=len(urls))
                    await record_billing(db, session_id=session_id, provider_id=img_prov.id,
                        billing_type=img_prov.billing_type.value, tokens_in=t_in, tokens_out=t_out,
                        cost=step_cost, currency=img_prov.currency,
                        detail={"type": "image_gen", "plan": "iterative", "step_index": idx, "image_count": len(urls)})
            else:
                logger.warning(f"execute_iterative: step {idx+1} returned no images")
            total_t_in += t_in
            total_t_out += t_out
            step_results.append({"step_index": idx, "images": urls, "tokens_in": t_in, "tokens_out": t_out})
        except Exception as e:
            logger.error(f"Iterative step {idx} failed: {e}")
            step_results.append({"step_index": idx, "images": [], "tokens_in": 0, "tokens_out": 0, "error": str(e)})

    logger.info(
        f"execute_iterative: completed, "
        f"total_images={len(all_images)}, "
        f"tokens_in={total_t_in}, tokens_out={total_t_out}"
    )

    task_manager.update_task(session_id, TaskStatus.IDLE)
    return {
        "images": all_images,
        "steps": step_results,
        "strategy": "iterative",
        "tokens_in": total_t_in,
        "tokens_out": total_t_out,
        "cost": total_cost,
        "cancelled": False,
    }
