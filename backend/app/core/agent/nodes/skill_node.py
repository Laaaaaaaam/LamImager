import logging

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.agent.state import AgentState
from app.models.skill import Skill
from app.services.skill_engine import apply_skill, skill_to_planner_hints

logger = logging.getLogger(__name__)


async def skill_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db = conf.get("db")
    prompt = state.get("prompt", "")
    skill_ids = state.get("skill_ids", [])

    if not skill_ids or not db:
        return {"skill_hints": None}

    hints_list: list[dict] = []
    for sid in skill_ids:
        result = await db.execute(select(Skill).where(Skill.id == sid))
        skill = result.scalar_one_or_none()
        if not skill:
            logger.warning(f"skill_node: skill {sid} not found, skipping")
            continue

        applied = apply_skill(prompt=prompt, skill=skill)
        if isinstance(applied, dict) and "strategy_hint" in applied:
            hints_list.append(applied)
        elif isinstance(applied, dict):
            hints_list.append(skill_to_planner_hints(skill))

    if not hints_list:
        return {"skill_hints": None}

    merged: dict = {
        "skill_id": hints_list[0].get("skill_id", ""),
        "skill_name": hints_list[0].get("skill_name", ""),
        "strategy_hint": hints_list[0].get("strategy_hint", ""),
        "planning_bias": {},
        "constraints": {},
        "prompt_bias": {},
    }
    for h in hints_list:
        if h.get("strategy_hint"):
            merged["strategy_hint"] = h["strategy_hint"]
        if h.get("planning_bias"):
            merged["planning_bias"].update(h["planning_bias"])
        if h.get("constraints"):
            merged["constraints"].update(h["constraints"])
        if h.get("prompt_bias"):
            merged["prompt_bias"].update(h["prompt_bias"])

    logger.info(
        f"skill_node: merged hints, strategy_hint={merged.get('strategy_hint')}, "
        f"constraints={list(merged.get('constraints', {}).keys())}"
    )

    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager
    _tm = conf.get("task_manager") or TaskManager()
    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{state.get('session_id', '')}",
        payload={
            "type": "agent_node_progress",
            "session_id": state.get("session_id", ""),
            "node": "skill",
            "status": "done",
            "message": "加载技能偏置",
            "content": f"加载偏置：{merged.get('strategy_hint', '无')}",
            "detail": {"strategy_hint": merged.get("strategy_hint", "")},
        },
    ))

    return {"skill_hints": merged}
