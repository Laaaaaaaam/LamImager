from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.execution import ExecutionPlan, ExecutionTrace
from app.schemas.planning import PlanningContext
from app.services.executors.single import SingleExecutor
from app.services.executors.parallel import ParallelExecutor
from app.services.executors.iterative import IterativeExecutor
from app.services.executors.radiate import RadiateExecutor
from app.services.task_manager import TaskManager

logger = logging.getLogger(__name__)

_EXECUTORS = {
    "single": SingleExecutor,
    "parallel": ParallelExecutor,
    "iterative": IterativeExecutor,
    "radiate": RadiateExecutor,
}


class PlanExecutionService:
    def __init__(self) -> None:
        self._executors: dict[str, SingleExecutor | ParallelExecutor | IterativeExecutor | RadiateExecutor] = {
            key: cls() for key, cls in _EXECUTORS.items()
        }

    async def execute(
        self,
        db: AsyncSession,
        plan: ExecutionPlan,
        context: PlanningContext,
        task_manager: TaskManager,
    ) -> ExecutionTrace:
        executor = self._executors.get(plan.strategy)
        if not executor:
            return ExecutionTrace(
                plan_id=plan.id,
                strategy=plan.strategy,
                status="failed",
                error=f"未知策略: {plan.strategy}",
            )

        return await executor.execute(db, plan, context, task_manager)
