from __future__ import annotations

import base64
import io
import logging

import aiohttp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider
from app.models.message import Message
from app.schemas.execution import Artifact, ExecutionPlan, ExecutionTrace, StepTrace
from app.schemas.planning import PlanningContext
from app.services.api_manager import resolve_provider_vendor
from app.services.billing_service import calc_cost, record_billing
from app.services.executors.utils import get_provider, now_iso
from app.services.task_manager import TaskManager, TaskStatus
from app.utils.image_client import ImageClient

logger = logging.getLogger(__name__)


class RadiateExecutor:
    async def execute(
        self,
        db: AsyncSession,
        plan: ExecutionPlan,
        context: PlanningContext,
        task_manager: TaskManager,
    ) -> ExecutionTrace:
        items = plan.plan_meta.get("items") or []
        if isinstance(items, dict):
            logger.warning("RadiateExecutor: items is dict instead of list, discarding")
            items = []
        n_items = len(items) if items else 0

        anchor_step_count = 1
        total_steps = anchor_step_count + n_items
        trace = ExecutionTrace(
            plan_id=plan.id,
            strategy="radiate",
            step_traces=[StepTrace(step_index=i, status="pending") for i in range(total_steps)],
            status="running",
        )

        if n_items == 0:
            trace.status = "failed"
            trace.error = "套图辐射需要至少 1 个子项"
            return trace

        if not context.image_provider_id:
            trace.status = "failed"
            trace.error = "未配置图像生成API"
            return trace

        provider = await get_provider(db, context.image_provider_id)
        if not provider:
            trace.status = "failed"
            trace.error = "图像生成API未找到"
            return trace

        try:
            base_url, api_key = await resolve_provider_vendor(db, provider)
        except Exception as e:
            trace.status = "failed"
            trace.error = f"API密钥解密失败: {e}"
            return trace

        client = ImageClient(base_url, api_key, provider.model_id)

        style_desc = plan.plan_meta.get("style", "")
        theme = plan.plan_meta.get("overall_theme", "")
        if not style_desc:
            style_desc = await self._extract_style_from_session(db, context)
            theme = style_desc

        cols, rows = _compute_grid_config(n_items)

        anchor_st = trace.step_traces[0]
        anchor_st.status = "running"
        anchor_st.started_at = now_iso()

        task_manager.update_task(
            context.session_id, TaskStatus.GENERATING,
            message=f"生成风格锚点图 ({cols}x{rows}, 4096x4096)",
        )

        item_descs = ", ".join([it.get("prompt", "") for it in items[:8]])
        anchor_prompt = f"A {cols}x{rows} grid showing {item_descs}. {style_desc} style, matching visual theme. Each cell distinctly separated with clear boundaries. Consistent art style across all cells."

        logger.info(f"RadiateExecutor: generating anchor grid, grid={cols}x{rows}")

        try:
            anchor_urls = []
            for sz in ["4096x4096", "2048x2048", "1024x1024"]:
                response = await client.generate(prompt=anchor_prompt, n=1, size=sz)
                anchor_urls = ImageClient.extract_images(response)
                if anchor_urls:
                    break

            if not anchor_urls:
                anchor_st.status = "failed"
                anchor_st.error = "锚点网格图生成失败"
                anchor_st.completed_at = now_iso()
                trace.status = "failed"
                trace.error = "锚点网格图生成失败"
                return trace

            anchor_url = anchor_urls[0]
            anchor_st.artifacts.append(Artifact(type="image", url=anchor_url, metadata={"role": "anchor_grid"}))

            anchor_usage = response.get("usage", {}) if isinstance(response, dict) else {}
            anchor_t_in = anchor_usage.get("prompt_tokens", 0)
            anchor_t_out = anchor_usage.get("completion_tokens", 0)
            anchor_cost = calc_cost(provider, tokens_in=anchor_t_in, tokens_out=anchor_t_out, call_count=1)
            await record_billing(
                db, session_id=context.session_id, provider_id=provider.id,
                billing_type=provider.billing_type.value,
                tokens_in=anchor_t_in, tokens_out=anchor_t_out,
                cost=anchor_cost, currency=provider.currency,
                detail={"type": "image_gen", "plan_strategy": "radiate", "radiate": "anchor_grid"},
            )
            anchor_st.tokens_in = anchor_t_in
            anchor_st.tokens_out = anchor_t_out
            anchor_st.cost = anchor_cost
            anchor_st.status = "completed"
            anchor_st.completed_at = now_iso()
            trace.total_tokens_in += anchor_t_in
            trace.total_tokens_out += anchor_t_out
            trace.total_cost += anchor_cost

            logger.info(f"RadiateExecutor: anchor grid ready, expanding ({n_items} items)")

            grid_images = await _crop_grid(anchor_url, cols, rows)

            if not grid_images or len(grid_images) < n_items:
                logger.warning(f"Grid crop failed: got {len(grid_images or [])} cells, need {n_items}, falling back to direct generation")
                await self._expand_fallback(
                    db, context, task_manager, trace, client, provider,
                    items, n_items, style_desc, anchor_step_count,
                )
            else:
                await self._expand_with_grid(
                    db, context, task_manager, trace, client, provider,
                    items, n_items, style_desc, grid_images, anchor_step_count,
                )

            trace.status = "completed"

        except Exception as e:
            logger.error(f"RadiateExecutor failed: {e}")
            trace.status = "failed"
            trace.error = str(e)

        return trace

    async def _expand_with_grid(
        self,
        db: AsyncSession,
        context: PlanningContext,
        task_manager: TaskManager,
        trace: ExecutionTrace,
        client: ImageClient,
        provider: ApiProvider,
        items: list[dict],
        n_items: int,
        style_desc: str,
        grid_images: list[str],
        anchor_step_count: int,
    ) -> None:
        reference_images = context.reference_images or None
        reference_labels = context.reference_labels or None

        for i in range(n_items):
            st = trace.step_traces[anchor_step_count + i]
            st.status = "running"
            st.started_at = now_iso()

            item = items[i] if i < len(items) else {}
            item_prompt = item.get("prompt", f"item {i+1}")

            task_manager.update_task(
                context.session_id, TaskStatus.GENERATING,
                progress=i + 1, total=n_items,
                message=f"生成子项 {i + 1}/{n_items}: {item_prompt[:30]}",
            )

            try:
                edit_images = [grid_images[i]]
                if reference_images:
                    edit_images.extend(reference_images[:3])
                response = await client.chat_edit(
                    prompt=f"{item_prompt}. {style_desc} style.",
                    images=edit_images,
                    reference_labels=reference_labels,
                )
                urls = ImageClient.extract_images_from_chat(response)
                if urls:
                    for url in urls:
                        st.artifacts.append(Artifact(type="image", url=url, metadata={"item_index": i}))
                    item_usage = response.get("usage", {}) if isinstance(response, dict) else {}
                    item_t_in = item_usage.get("prompt_tokens", 0)
                    item_t_out = item_usage.get("completion_tokens", 0)
                    item_cost = calc_cost(provider, tokens_in=item_t_in, tokens_out=item_t_out, call_count=len(urls))
                    await record_billing(
                        db, session_id=context.session_id, provider_id=provider.id,
                        billing_type=provider.billing_type.value,
                        tokens_in=item_t_in, tokens_out=item_t_out,
                        cost=item_cost, currency=provider.currency,
                        detail={"type": "image_gen", "plan_strategy": "radiate", "radiate": "item", "item_index": i},
                    )
                    st.tokens_in = item_t_in
                    st.tokens_out = item_t_out
                    st.cost = item_cost
                    trace.total_tokens_in += item_t_in
                    trace.total_tokens_out += item_t_out
                    trace.total_cost += item_cost

                st.status = "completed"
                st.completed_at = now_iso()

            except Exception as e:
                logger.warning(f"RadiateExecutor grid expand item #{i} failed: {e}")
                st.status = "failed"
                st.error = str(e)
                st.completed_at = now_iso()

    async def _expand_fallback(
        self,
        db: AsyncSession,
        context: PlanningContext,
        task_manager: TaskManager,
        trace: ExecutionTrace,
        client: ImageClient,
        provider: ApiProvider,
        items: list[dict],
        n_items: int,
        style_desc: str,
        anchor_step_count: int,
    ) -> None:
        reference_images = context.reference_images or None
        reference_labels = context.reference_labels or None

        for i in range(n_items):
            st = trace.step_traces[anchor_step_count + i]
            st.status = "running"
            st.started_at = now_iso()

            item = items[i] if i < len(items) else {}
            item_prompt = item.get("prompt", f"item {i+1}")

            task_manager.update_task(
                context.session_id, TaskStatus.GENERATING,
                progress=i + 1, total=n_items,
                message=f"直接生成子项 {i + 1}/{n_items}: {item_prompt[:30]}",
            )

            try:
                if reference_images:
                    response = await client.chat_edit(
                        prompt=f"{item_prompt}. {style_desc} style.",
                        images=reference_images[:4],
                        reference_labels=reference_labels,
                    )
                    urls = ImageClient.extract_images_from_chat(response)
                else:
                    response = await client.generate(
                        prompt=f"{item_prompt}. {style_desc} style.",
                        n=1,
                        size="1024x1024",
                    )
                    urls = ImageClient.extract_images(response)

                if urls:
                    for url in urls:
                        st.artifacts.append(Artifact(type="image", url=url, metadata={"item_index": i}))
                    item_usage = response.get("usage", {}) if isinstance(response, dict) else {}
                    item_t_in = item_usage.get("prompt_tokens", 0)
                    item_t_out = item_usage.get("completion_tokens", 0)
                    item_cost = calc_cost(provider, tokens_in=item_t_in, tokens_out=item_t_out, call_count=len(urls))
                    await record_billing(
                        db, session_id=context.session_id, provider_id=provider.id,
                        billing_type=provider.billing_type.value,
                        tokens_in=item_t_in, tokens_out=item_t_out,
                        cost=item_cost, currency=provider.currency,
                        detail={"type": "image_gen", "plan_strategy": "radiate", "radiate": "item_fallback", "item_index": i},
                    )
                    st.tokens_in = item_t_in
                    st.tokens_out = item_t_out
                    st.cost = item_cost
                    trace.total_tokens_in += item_t_in
                    trace.total_tokens_out += item_t_out
                    trace.total_cost += item_cost

                st.status = "completed"
                st.completed_at = now_iso()

            except Exception as e:
                logger.warning(f"RadiateExecutor fallback item #{i} failed: {e}")
                st.status = "failed"
                st.error = str(e)
                st.completed_at = now_iso()

    async def _extract_style_from_session(self, db: AsyncSession, context: PlanningContext) -> str:
        msg_result = await db.execute(
            select(Message).where(
                Message.session_id == context.session_id,
                Message.role == "user",
            ).order_by(Message.created_at.desc()).limit(1),
        )
        user_msg = msg_result.scalars().first()
        user_text = user_msg.content if user_msg else context.prompt
        return _extract_style_from_text(user_text)


def _compute_grid_config(n: int) -> tuple[int, int]:
    if n <= 2:
        return 1, n
    elif n <= 4:
        return 2, (n + 1) // 2
    elif n <= 9:
        return 3, (n + 2) // 3
    else:
        return 4, (n + 3) // 4


async def _crop_grid(image_url: str, cols: int, rows: int) -> list[str]:
    try:
        from PIL import Image as PILImage
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
