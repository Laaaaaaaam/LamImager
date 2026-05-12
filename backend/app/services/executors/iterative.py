from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.execution import Artifact, ExecutionPlan, ExecutionTrace, StepTrace
from app.schemas.planning import PlanningContext
from app.services.billing_service import calc_cost, record_billing
from app.services.executors.utils import get_provider, now_iso, resolve_context_references
from app.services.task_manager import TaskManager, TaskStatus

logger = logging.getLogger(__name__)


class IterativeExecutor:
    async def execute(
        self,
        db: AsyncSession,
        plan: ExecutionPlan,
        context: PlanningContext,
        task_manager: TaskManager,
    ) -> ExecutionTrace:
        trace = ExecutionTrace(
            plan_id=plan.id,
            strategy="iterative",
            step_traces=[StepTrace(step_index=i, status="pending") for i in range(len(plan.steps))],
            status="running",
        )

        if not plan.steps:
            trace.status = "failed"
            trace.error = "没有可执行的步骤"
            return trace

        if not context.image_provider_id:
            trace.status = "failed"
            trace.error = "未配置图像生成API"
            return trace

        img_prov = await get_provider(db, context.image_provider_id)
        ref_images: list[str] | None = await resolve_context_references(plan, context)

        for idx, step in enumerate(plan.steps):
            st = trace.step_traces[idx]
            st.status = "running"
            st.started_at = now_iso()
            desc = step.description or step.prompt[:60]

            task_manager.update_task(
                context.session_id, TaskStatus.GENERATING,
                progress=idx + 1, total=len(plan.steps),
                message=f"步骤 {idx + 1}/{len(plan.steps)}: {desc[:40]}",
            )

            try:
                from app.services.generate_service import generate_images_core
                urls, t_in, t_out = await generate_images_core(
                    db=db,
                    provider_id=context.image_provider_id,
                    prompt=step.prompt,
                    image_count=step.image_count,
                    image_size=step.image_size or context.image_size,
                    negative_prompt=step.negative_prompt or context.negative_prompt,
                    reference_images=ref_images,
                    reference_labels=context.reference_labels or None,
                    session_id=context.session_id,
                )

                if urls:
                    ref_images = urls[:1]

                for url in urls:
                    st.artifacts.append(Artifact(type="image", url=url))
                st.tokens_in = t_in
                st.tokens_out = t_out
                st.status = "completed"
                st.completed_at = now_iso()

                trace.total_tokens_in += t_in
                trace.total_tokens_out += t_out

                if urls and img_prov:
                    step_cost = calc_cost(img_prov, tokens_in=t_in, tokens_out=t_out, call_count=len(urls))
                    await record_billing(
                        db, session_id=context.session_id, provider_id=img_prov.id,
                        billing_type=img_prov.billing_type.value,
                        tokens_in=t_in, tokens_out=t_out,
                        cost=step_cost, currency=img_prov.currency,
                        detail={"type": "image_gen", "plan_strategy": "iterative", "step_index": idx, "image_count": len(urls)},
                    )
                    trace.total_cost += step_cost
                    st.cost = step_cost

            except Exception as e:
                logger.error(f"IterativeExecutor step {idx} failed: {e}")
                st.status = "failed"
                st.error = str(e)
                st.completed_at = now_iso()

        trace.status = "completed"
        return trace
