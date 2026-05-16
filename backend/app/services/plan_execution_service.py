import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.execution import ExecutionPlan, ExecutionTrace
from app.schemas.planning import PlanningContext
from app.services.executors.engine import ExecutionEngine
from app.services.task_manager import TaskManager

logger = logging.getLogger(__name__)


class PlanExecutionService:
    async def execute(
        self,
        db: AsyncSession,
        plan: ExecutionPlan,
        context: PlanningContext,
        task_manager: TaskManager,
    ) -> ExecutionTrace:
        engine = ExecutionEngine(plan, context)
        return await engine.run_all(db, task_manager)
