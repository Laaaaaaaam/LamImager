from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.execution import Artifact, ExecutionPlan, ExecutionTrace, StepTrace
from app.schemas.planning import PlanningContext
from app.services.billing_service import calc_cost, record_billing
from app.services.executors.utils import get_provider, now_iso, resolve_context_references
from app.services.task_manager import TaskManager, TaskStatus

logger = logging.getLogger(__name__)


class SingleExecutor:
    async def execute(
        self,
        db: AsyncSession,
        plan: ExecutionPlan,
        context: PlanningContext,
        task_manager: TaskManager,
    ) -> ExecutionTrace:
        trace = ExecutionTrace(
            plan_id=plan.id,
            strategy="single",
            step_traces=[StepTrace(step_index=0, status="pending")],
            status="running",
        )

        if not context.image_provider_id:
            trace.status = "failed"
            trace.error = "未配置图像生成API"
            return trace

        step = plan.steps[0] if plan.steps else None
        if not step:
            trace.status = "failed"
            trace.error = "没有可执行的步骤"
            return trace

        st = trace.step_traces[0]
        st.status = "running"
        st.started_at = now_iso()

        image_count = step.image_count or context.image_count
        image_size = step.image_size or context.image_size

        task_manager.update_task(
            context.session_id, TaskStatus.GENERATING,
            message=f"单图生成 | 生成 {image_count} 张图片",
        )

        reference_images = await resolve_context_references(plan, context)

        try:
            from app.services.generate_service import generate_images_core
            urls, tokens_in, tokens_out = await generate_images_core(
                db=db,
                provider_id=context.image_provider_id,
                prompt=step.prompt,
                image_count=image_count,
                image_size=image_size,
                negative_prompt=step.negative_prompt or context.negative_prompt,
                reference_images=reference_images,
                reference_labels=context.reference_labels or None,
                session_id=context.session_id,
            )

            for url in urls:
                st.artifacts.append(Artifact(type="image", url=url))

            st.tokens_in = tokens_in
            st.tokens_out = tokens_out
            st.status = "completed"
            st.completed_at = now_iso()

            trace.total_tokens_in = tokens_in
            trace.total_tokens_out = tokens_out

            if urls:
                img_prov = await get_provider(db, context.image_provider_id)
                if img_prov:
                    step_cost = calc_cost(img_prov, tokens_in=tokens_in, tokens_out=tokens_out, call_count=len(urls))
                    await record_billing(
                        db, session_id=context.session_id, provider_id=img_prov.id,
                        billing_type=img_prov.billing_type.value,
                        tokens_in=tokens_in, tokens_out=tokens_out,
                        cost=step_cost, currency=img_prov.currency,
                        detail={"type": "image_gen", "plan_strategy": "single", "image_count": len(urls)},
                    )
                    trace.total_cost = step_cost
                    st.cost = step_cost

            trace.status = "completed"

        except Exception as e:
            logger.error(f"SingleExecutor failed: {e}")
            st.status = "failed"
            st.error = str(e)
            st.completed_at = now_iso()
            trace.status = "failed"
            trace.error = str(e)

        return trace
