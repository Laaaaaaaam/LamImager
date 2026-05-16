import logging

from langchain_core.runnables import RunnableConfig

from app.core.agent.state import AgentState

logger = logging.getLogger(__name__)


def _match_score(
    intent_text: str,
    skill_text: str,
    task_type: str,
    strategy_hint: str,
) -> float:
    score = 0.0

    intent_words = set(intent_text.split())
    skill_words = set(skill_text.split())
    if skill_words:
        overlap = len(intent_words & skill_words)
        score += min(overlap / len(skill_words), 1.0) * 0.5

    if strategy_hint and strategy_hint.lower() == task_type:
        score += 0.3

    if any(kw in intent_text for kw in list(skill_words)[:3]):
        score += 0.2

    return min(score, 1.0)


async def skill_matcher_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db = conf.get("db")
    intent = state.get("intent", {})
    user_skill_ids = state.get("skill_ids", []) or []

    task_type = intent.get("task_type", "single")
    user_goal = intent.get("user_goal", "")
    items = intent.get("items", [])

    if not db:
        return {"skill_ids": user_skill_ids}

    from sqlalchemy import select
    from app.models.skill import Skill

    result = await db.execute(select(Skill))
    skills = result.scalars().all()

    if not skills:
        return {"skill_ids": user_skill_ids}

    intent_text = f"{user_goal} {' '.join(i.get('label', '') for i in items)}".lower()

    scored: list[tuple[float, str]] = []
    for skill in skills:
        skill_text = f"{skill.name or ''} {skill.description or ''}".lower()
        strategy_hint = skill.strategy_hint or ""
        score = _match_score(intent_text, skill_text, task_type, strategy_hint)

        if score >= 0.3:
            scored.append((score, skill.id))

    scored.sort(reverse=True)
    matched_ids = [sid for _, sid in scored[:3]]
    matched_names = [skill.name for skill in skills if skill.id in matched_ids]

    merged = list(dict.fromkeys(user_skill_ids + matched_ids))

    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager
    _tm = conf.get("task_manager") or TaskManager()
    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{state.get('session_id', '')}",
        payload={
            "type": "agent_node_progress",
            "session_id": state.get("session_id", ""),
            "node": "skill_matcher",
            "status": "done",
            "message": "匹配技能",
            "content": f"匹配到 {len(matched_ids)} 个技能：{', '.join(matched_names) if matched_names else '无'}",
            "detail": {"matched_count": len(matched_ids)},
        },
    ))

    logger.info(
        f"skill_matcher_node: user={user_skill_ids}, "
        f"matched={matched_ids}, merged={merged}"
    )
    return {"skill_ids": merged}
