import logging

from langchain_core.runnables import RunnableConfig

from app.core.agent.state import AgentState

logger = logging.getLogger(__name__)


def _find_lowest_score_step(critic_results: list[dict], plan_steps: list[dict]) -> int:
    if not critic_results or not plan_steps:
        return -1
    min_score = float("inf")
    min_idx = -1
    for i, cr in enumerate(critic_results):
        score = cr.get("score", 7.0)
        if score < min_score:
            min_score = score
            min_idx = i
    if min_idx >= len(plan_steps):
        min_idx = len(plan_steps) - 1
    return max(0, min_idx)


async def decision_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    critic_results = state.get("critic_results", [])
    retry_count = state.get("retry_count", 0)

    planning_ctx = state.get("planning_context", {})
    critic_max_retry = 2
    if isinstance(planning_ctx, dict):
        critic_max_retry = planning_ctx.get("critic_max_retry", 2)

    if not critic_results:
        await _publish_decision(state, config, "pass", 0.0)
        return {"decision_result": "pass", "status": "completed", "retry_step_index": -1}

    avg_score = sum(r.get("score", 7.0) for r in critic_results) / len(critic_results)
    all_issues: list[str] = []
    for r in critic_results:
        all_issues.extend(r.get("issues", []))

    plan_dict = state.get("execution_plan", {})
    plan_steps = plan_dict.get("steps", []) if isinstance(plan_dict, dict) else []
    lowest_step = _find_lowest_score_step(critic_results, plan_steps)

    if retry_count >= critic_max_retry:
        logger.info(
            f"decision_node: retry_count={retry_count} >= max={critic_max_retry}, "
            f"accepting with score={avg_score:.1f}"
        )
        await _publish_decision(state, config, "pass", avg_score)
        return {"decision_result": "pass", "status": "completed", "retry_step_index": -1}

    if avg_score >= 7.0:
        logger.info(f"decision_node: score={avg_score:.1f} >= 7.0, pass")
        await _publish_decision(state, config, "pass", avg_score)
        return {"decision_result": "pass", "status": "completed", "retry_step_index": -1}

    if avg_score >= 5.0:
        logger.info(f"decision_node: score={avg_score:.1f} in [5.0, 7.0), warn (output but mark)")
        await _publish_decision(state, config, "pass", avg_score)
        return {"decision_result": "pass", "status": "completed", "retry_step_index": -1}

    if avg_score >= 3.0:
        has_prompt_issues = any(
            kw in " ".join(all_issues)
            for kw in ["构图", "色调", "风格", "细节", "模糊", "光照", "composition", "color", "style", "detail", "blur", "lighting"]
        )
        if has_prompt_issues:
            logger.info(
                f"decision_node: score={avg_score:.1f} in [3.0, 5.0), "
                f"prompt-related issues → retry_prompt (step {lowest_step})"
            )
            await _publish_decision(state, config, "retry_prompt", avg_score)
            return {
                "decision_result": "retry_prompt",
                "retry_count": retry_count + 1,
                "retry_step_index": lowest_step,
                "status": "retry_prompt",
            }
        else:
            logger.info(
                f"decision_node: score={avg_score:.1f} in [3.0, 5.0), "
                f"execution issues → retry_step (step {lowest_step})"
            )
            await _publish_decision(state, config, "retry_step", avg_score)
            return {
                "decision_result": "retry_step",
                "retry_count": retry_count + 1,
                "retry_step_index": lowest_step,
                "status": "retry_step",
            }

    logger.info(
        f"decision_node: score={avg_score:.1f} < 3.0, severe defects → retry_step (step {lowest_step})"
    )
    await _publish_decision(state, config, "retry_step", avg_score)
    return {
        "decision_result": "retry_step",
        "retry_count": retry_count + 1,
        "retry_step_index": lowest_step,
        "status": "retry_step",
    }


async def _publish_decision(state: AgentState, config: RunnableConfig, result: str, avg_score: float) -> None:
    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager
    _tm = config.get("configurable", {}).get("task_manager") or TaskManager()
    message_map = {"pass": "通过", "retry_prompt": "重试提示词", "retry_step": "重试执行", "replan": "重新规划"}
    reason_map = {"pass": "评分达标", "retry_prompt": "提示词相关问题", "retry_step": "执行质量问题", "replan": "需要重新规划"}
    if result == "pass":
        content = f"通过（{avg_score:.1f} ≥ 7.0）"
    else:
        content = f"重试（{result}, 均分 {avg_score:.1f}）"
    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{state.get('session_id', '')}",
        payload={
            "type": "agent_node_progress",
            "session_id": state.get("session_id", ""),
            "node": "decision",
            "status": "done",
            "message": message_map.get(result, result),
            "content": content,
            "detail": {"result": result, "avg_score": round(avg_score, 1)},
        },
    ))
