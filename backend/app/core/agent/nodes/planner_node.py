import json
import logging
import re

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.agent.state import AgentState
from app.core.agent.capability_prompts import build_planner_system_prompt
from app.core.agent.llm_call_logger import LLMCallRecord, extract_tokens, log_and_bill, LLMTimer
from app.schemas.execution import ExecutionPlan, PlanStep
from app.services.agent_intent_service import STRATEGY_MAP
from app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

STRATEGY_WHITELIST: dict[str, list[str]] = {
    "single": ["single"],
    "multi_independent": ["parallel"],
    "iterative": ["iterative"],
    "radiate": ["radiate"],
}


def _fallback_plan(
    prompt: str,
    task_type: str,
    image_count: int,
    image_size: str,
    negative_prompt: str,
    intent: dict,
    context_reference_urls: list[str],
) -> ExecutionPlan:
    strategy = STRATEGY_MAP.get(task_type, "single")
    return ExecutionPlan(
        strategy=strategy,
        steps=[PlanStep(
            index=0,
            prompt=prompt,
            negative_prompt=negative_prompt,
            image_count=image_count,
            image_size=image_size,
        )],
        intent_meta=intent,
        plan_meta={"context_reference_urls": context_reference_urls, "fallback": True},
        source="planner_fallback",
    )


async def planner_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db = conf.get("db")

    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager
    _tm = conf.get("task_manager") or TaskManager()

    intent = state.get("intent", {})
    task_type = intent.get("task_type", "single")
    expected_count = intent.get("expected_count", 1)
    prompt = state.get("prompt", "")
    image_count = state.get("image_count", 1)
    image_size = state.get("image_size", "1024x1024")
    negative_prompt = state.get("negative_prompt", "")
    context_reference_urls = list(state.get("context_reference_urls", []))
    context_images = state.get("context_images", []) or None
    skill_hints = state.get("skill_hints")

    llm_provider_id = state.get("llm_provider_id", "")
    if not db or not llm_provider_id:
        plan = _fallback_plan(
            prompt, task_type, image_count or expected_count,
            image_size, negative_prompt, intent, context_reference_urls,
        )
        return {"execution_plan": plan.model_dump(), "status": "plan_ready"}

    from app.models.api_provider import ApiProvider
    from app.services.generate_service import resolve_provider_vendor

    result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        plan = _fallback_plan(
            prompt, task_type, image_count or expected_count,
            image_size, negative_prompt, intent, context_reference_urls,
        )
        return {"execution_plan": plan.model_dump(), "status": "plan_ready"}

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        logger.warning(f"planner_node: LLM key decrypt failed: {e}")
        plan = _fallback_plan(
            prompt, task_type, image_count or expected_count,
            image_size, negative_prompt, intent, context_reference_urls,
        )
        return {"execution_plan": plan.model_dump(), "status": "plan_ready"}

    whitelist = STRATEGY_WHITELIST.get(task_type, ["single"])
    constraints_str = ""
    if skill_hints and isinstance(skill_hints, dict):
        c = skill_hints.get("constraints", {})
        if c:
            constraints_str = json.dumps(c, ensure_ascii=False)
        hint = skill_hints.get("strategy_hint", "")
        if hint:
            constraints_str += f"\n- Strategy hint: {hint}"

    system_prompt = build_planner_system_prompt(
        task_type=task_type,
        strategy_whitelist=whitelist,
        image_size=image_size,
        skill_constraints=constraints_str,
        model_id=provider.model_id,
        supported_sizes=image_size,
    )

    user_data = {
        "request": prompt,
        "task_type": task_type,
        "expected_count": expected_count,
        "image_count": image_count,
        "items": intent.get("items", []),
        "references": intent.get("references", []),
        "search_context": state.get("search_context", ""),
    }

    planning_ctx = state.get("planning_context", {})
    if isinstance(planning_ctx, dict):
        image_descriptions = planning_ctx.get("image_descriptions", {})
        if image_descriptions:
            user_data["context_image_descriptions"] = image_descriptions

    critic_results = state.get("critic_results", [])
    if critic_results:
        previous_issues = []
        for cr in critic_results:
            previous_issues.extend(cr.get("issues", []))
        avg_score = sum(cr.get("score", 0) for cr in critic_results) / len(critic_results) if critic_results else 0
        user_data["previous_issues"] = previous_issues
        user_data["previous_avg_score"] = avg_score
        user_data["replan_reason"] = f"Previous plan scored {avg_score:.1f}/10. Issues: {'; '.join(previous_issues[:5])}"

    user_msg = json.dumps(user_data, ensure_ascii=False)

    client = LLMClient(base_url=base_url, api_key=api_key, model_id=provider.model_id)

    plan_dict = None
    for attempt in range(2):
        try:
            messages = [{"role": "system", "content": system_prompt}]
            log_user_content = user_msg
            if context_images:
                user_content: str | list[dict] = [
                    {"type": "text", "text": user_msg},
                ]
                for idx, img_url in enumerate(context_images[:2]):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": img_url, "detail": "auto"},
                    })
                messages.append({"role": "user", "content": user_content})
                log_user_content = json.dumps(user_content, ensure_ascii=False)
            else:
                messages.append({"role": "user", "content": user_msg})

            with LLMTimer() as timer:
                full_text = ""
                usage_data = None
                async for delta, usage in client.chat_stream(messages, temperature=0.7):
                    full_text += delta
                    await _tm.publish(LamEvent(
                        event_type="task_progress",
                        correlation_id=f"agent-{state.get('session_id', '')}",
                        payload={
                            "type": "agent_token",
                            "session_id": state.get("session_id", ""),
                            "node": "planner",
                            "content": delta,
                        },
                    ))
                    if usage:
                        usage_data = usage
            t_in = usage_data.get("prompt_tokens", 0) if usage_data else 0
            t_out = usage_data.get("completion_tokens", 0) if usage_data else 0
            if t_in > 500000: t_in = 0
            if t_out > 100000: t_out = max(len(full_text) // 4, 0)
            text = full_text

            if db and llm_provider_id:
                await log_and_bill(db, LLMCallRecord(
                    node="planner",
                    model_id=provider.model_id,
                    provider_id=llm_provider_id,
                    session_id=state.get("session_id", ""),
                    tokens_in=t_in,
                    tokens_out=t_out,
                    latency_ms=timer.ms,
                    billing_type="agent",
                    system_prompt=system_prompt,
                    user_content=log_user_content,
                    response_text=text,
                    extra={"attempt": attempt + 1},
                ))
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            parsed = json.loads(text)
            if isinstance(parsed, dict) and parsed.get("steps"):
                plan_dict = parsed
                break
        except Exception as e:
            logger.warning(f"planner_node: LLM attempt {attempt + 1} failed: {e}")

    if not plan_dict:
        plan = _fallback_plan(
            prompt, task_type, image_count or expected_count,
            image_size, negative_prompt, intent, context_reference_urls,
        )
        return {"execution_plan": plan.model_dump(), "status": "plan_ready"}

    strategy = plan_dict.get("strategy", whitelist[0])
    if strategy not in whitelist:
        strategy = whitelist[0]

    steps_raw = plan_dict.get("steps", [])
    plan_steps: list[PlanStep] = []
    for i, s in enumerate(steps_raw):
        if not isinstance(s, dict) or not s.get("prompt"):
            continue
        plan_steps.append(PlanStep(
            index=i,
            prompt=str(s["prompt"]),
            negative_prompt=str(s.get("negative_prompt", "")),
            description=str(s.get("description", "")),
            image_count=int(s.get("image_count", 1)),
            image_size=str(s.get("image_size", image_size)),
            reference_step_indices=s.get("reference_step_indices"),
            checkpoint=s.get("checkpoint"),
        ))

    if not plan_steps:
        plan = _fallback_plan(
            prompt, task_type, image_count or expected_count,
            image_size, negative_prompt, intent, context_reference_urls,
        )
        return {"execution_plan": plan.model_dump(), "status": "plan_ready"}

    if strategy == "iterative" and len(plan_steps) > 1:
        has_checkpoint = any(s.checkpoint and s.checkpoint.get("enabled") for s in plan_steps)
        if not has_checkpoint:
            plan_steps[0].checkpoint = {"enabled": True}
        for i, s in enumerate(plan_steps):
            if i > 0 and not s.reference_step_indices:
                s.reference_step_indices = [i - 1]

    plan_meta = {
        "context_reference_urls": context_reference_urls,
        "skill_hints": skill_hints,
    }
    if strategy == "radiate":
        items_raw = plan_dict.get("plan_meta", {}).get("items", [])
        style_raw = plan_dict.get("plan_meta", {}).get("style", "")
        plan_meta.update({
            "items": items_raw,
            "style": style_raw,
            "overall_theme": plan_dict.get("plan_meta", {}).get("overall_theme", ""),
        })
        n_items = len(items_raw) if isinstance(items_raw, list) else 0
        if n_items > 0:
            from app.services.executors.engine import _compute_grid_config, _grid_position
            cols, rows = _compute_grid_config(n_items)
            for i, s in enumerate(plan_steps):
                if i > 0:
                    if not s.reference_step_indices:
                        s.reference_step_indices = [0]
                    row, col = _grid_position(i - 1, cols)
                    s.metadata["crop_from_anchor"] = True
                    s.metadata["crop_region"] = {"row": row, "col": col}
                    if style_raw:
                        s.metadata["prompt_suffix"] = f"{style_raw} style."

    plan = ExecutionPlan(
        strategy=strategy,
        steps=plan_steps,
        intent_meta=intent,
        plan_meta=plan_meta,
        source="planner_llm",
    )

    logger.info(
        f"planner_node: strategy={strategy}, steps={len(plan_steps)}, "
        f"source=planner_llm"
    )

    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{state.get('session_id', '')}",
        payload={
            "type": "agent_node_progress",
            "session_id": state.get("session_id", ""),
            "node": "planner",
            "status": "done",
            "message": "生成执行计划",
            "content": f"策略: {strategy}, {len(plan_steps)} 步\n" + "\n".join(f"  {i+1}. {s.description or s.prompt}" for i, s in enumerate(plan_steps[:8])),
            "detail": {"strategy": strategy, "steps": [{"index": s.index, "description": s.description or s.prompt[:80], "prompt": s.prompt, "image_count": s.image_count, "checkpoint": s.checkpoint} for s in plan_steps[:8]]},
        },
    ))

    return {"execution_plan": plan.model_dump(), "status": "plan_ready"}
