from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.execution import ExecutionPlan, ExecutionTrace
from app.schemas.planning import PlanningContext
from app.services.task_manager import TaskManager


@runtime_checkable
class BaseExecutor(Protocol):
    async def execute(
        self,
        db: AsyncSession,
        plan: ExecutionPlan,
        context: PlanningContext,
        task_manager: TaskManager,
    ) -> ExecutionTrace: ...
