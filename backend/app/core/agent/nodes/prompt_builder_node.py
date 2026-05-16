import json
import logging

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.agent.state import AgentState
from app.core.agent.capability_prompts import PROMPT_BUILDER_GUIDE, IMAGE_PROVIDER_CAPABILITIES
from app.core.agent.llm_call_logger import LLMCallRecord, extract_tokens, log_and_bill, LLMTimer
from app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _apply_prompt_bias(prompt: str, prompt_bias: dict) -> str:
    if not prompt_bias:
        return prompt

    detail_level = prompt_bias.get("detail_level", "")
    if detail_level == "rich":
        prompt += ", rich details, intricate textures"
    elif detail_level == "minimal":
        prompt += ", simple, clean"

    style = prompt_bias.get("style", "")
    if style:
        prompt += f", {style}"

    quality = prompt_bias.get("quality", "")
    if quality:
        prompt += f", {quality} quality"

    return prompt


def _build_bias_instruction(prompt_bias: dict) -> str:
    if not prompt_bias:
        return "none"

    parts = []
    detail_level = prompt_bias.get("detail_level", "")
    if detail_level == "rich":
        parts.append("Prefer rich visual detail and intricate textures where appropriate, but do not add generic quality keywords.")
    elif detail_level == "minimal":
        parts.append("Keep the prompt concise and minimal — avoid unnecessary elaboration.")

    style = prompt_bias.get("style", "")
    if style:
        parts.append(f"Incorporate the style '{style}' naturally into the prompt where it fits the intent.")

    quality = prompt_bias.get("quality", "")
    if quality:
        parts.append(f"Aim for {quality} quality output, but express this through specific visual characteristics rather than generic quality labels.")

    return "; ".join(parts) if parts else "none"


def _build_prompt_builder_system(skill_bias: str, model_id: str = "", supported_sizes: str = "") -> str:
    parts = [
        "You are an image generation prompt optimizer. "
        "Given a step prompt and optional context, optimize it for better image generation quality.\n\n",
        PROMPT_BUILDER_GUIDE,
        "\n\n",
        "Skill bias: ",
        skill_bias,
    ]
    if model_id:
        parts.append("\n\n")
        parts.append(IMAGE_PROVIDER_CAPABILITIES.format(model_id=model_id, supported_sizes=supported_sizes))
    return "".join(parts)


async def prompt_builder_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db = conf.get("db")

    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager
    _tm = conf.get("task_manager") or TaskManager()

    plan_dict = state.get("execution_plan")
    if not plan_dict:
        return {"optimized_prompts": [], "status": "error"}

    steps = plan_dict.get("steps", []) if isinstance(plan_dict, dict) else []
    if not steps:
        return {"optimized_prompts": [], "status": "error"}

    context_images = state.get("context_images", []) or None
    skill_hints = state.get("skill_hints")
    prompt_bias = {}
    if skill_hints and isinstance(skill_hints, dict):
        prompt_bias = skill_hints.get("prompt_bias", {})

    planning_ctx = state.get("planning_context", {})
    image_descriptions = {}
    if isinstance(planning_ctx, dict):
        image_descriptions = planning_ctx.get("image_descriptions", {})

    critic_results = state.get("critic_results", [])
    retry_step_index = state.get("retry_step_index", -1)

    llm_provider_id = state.get("llm_provider_id", "")
    optimized: list[str] = []

    if not db or not llm_provider_id:
        for step in steps:
            step_prompt = step.get("prompt", "") if isinstance(step, dict) else getattr(step, "prompt", "")
            optimized_prompt = _apply_prompt_bias(step_prompt, prompt_bias)
            optimized.append(optimized_prompt)
        return {"optimized_prompts": optimized, "status": "prompts_ready"}

    from app.models.api_provider import ApiProvider
    from app.services.generate_service import resolve_provider_vendor

    result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        for step in steps:
            step_prompt = step.get("prompt", "") if isinstance(step, dict) else getattr(step, "prompt", "")
            optimized_prompt = _apply_prompt_bias(step_prompt, prompt_bias)
            optimized.append(optimized_prompt)
        return {"optimized_prompts": optimized, "status": "prompts_ready"}

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception:
        for step in steps:
            step_prompt = step.get("prompt", "") if isinstance(step, dict) else getattr(step, "prompt", "")
            optimized_prompt = _apply_prompt_bias(step_prompt, prompt_bias)
            optimized.append(optimized_prompt)
        return {"optimized_prompts": optimized, "status": "prompts_ready"}

    client = LLMClient(base_url=base_url, api_key=api_key, model_id=provider.model_id)
    bias_instruction = _build_bias_instruction(prompt_bias)
    system_prompt = _build_prompt_builder_system(
        skill_bias=bias_instruction,
        model_id=provider.model_id,
        supported_sizes="1024x1024, 1024x1792, 1792x1024",
    )

    for step_idx, step in enumerate(steps):
        step_prompt = step.get("prompt", "") if isinstance(step, dict) else getattr(step, "prompt", "")
        if not step_prompt:
            optimized.append(step_prompt)
            continue

        desc_context = ""
        if image_descriptions:
            desc_parts = [f"- {url[:50]}: {desc}" for url, desc in image_descriptions.items()]
            desc_context = f"\n\nContext image descriptions:\n" + "\n".join(desc_parts)

        critic_feedback = ""
        if critic_results and retry_step_index >= 0 and step_idx == retry_step_index:
            step_issues = []
            for cr in critic_results:
                issues = cr.get("issues", [])
                if issues:
                    step_issues.extend(issues)
            if step_issues:
                critic_feedback = f"\n\nPrevious attempt issues: {'; '.join(step_issues)}. Fix these in the new prompt."
        elif critic_results and retry_step_index < 0:
            all_issues = []
            for cr in critic_results:
                all_issues.extend(cr.get("issues", []))
            if all_issues:
                critic_feedback = f"\n\nPrevious attempt issues: {'; '.join(all_issues[:5])}. Address these in the optimized prompt."

        try:
            user_content: str | list[dict]
            if context_images:
                user_content = [
                    {"type": "text", "text": f"Optimize this prompt: {step_prompt}{desc_context}{critic_feedback}"},
                ]
                for idx, img_url in enumerate(context_images[:2]):
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": img_url, "detail": "auto"},
                    })
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]
            else:
                user_content = f"{step_prompt}{desc_context}{critic_feedback}"
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ]

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
                            "node": "prompt_builder",
                            "content": delta,
                        },
                    ))
                    if usage:
                        usage_data = usage
            t_in = usage_data.get("prompt_tokens", 0) if usage_data else 0
            t_out = usage_data.get("completion_tokens", 0) if usage_data else 0
            if t_in > 500000: t_in = 0
            if t_out > 100000: t_out = max(len(full_text) // 4, 0)
            result_text = full_text

            if db and llm_provider_id:
                user_content_str = json.dumps(user_content, ensure_ascii=False) if isinstance(user_content, list) else str(user_content)
                await log_and_bill(db, LLMCallRecord(
                    node="prompt_builder",
                    model_id=provider.model_id,
                    provider_id=llm_provider_id,
                    session_id=state.get("session_id", ""),
                    tokens_in=t_in,
                    tokens_out=t_out,
                    latency_ms=timer.ms,
                    billing_type="agent",
                    system_prompt=system_prompt,
                    user_content=user_content_str,
                    response_text=result_text or "",
                    extra={"step_index": step_idx},
                ))
            if result_text and result_text.strip():
                optimized.append(result_text.strip())
            else:
                optimized.append(step_prompt)
        except Exception as e:
            logger.warning(f"prompt_builder_node: optimization failed for step, using original prompt: {e}")
            optimized.append(step_prompt)

    logger.info(f"prompt_builder_node: optimized {len(optimized)} prompts")

    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{state.get('session_id', '')}",
        payload={
            "type": "agent_node_progress",
            "session_id": state.get("session_id", ""),
            "node": "prompt_builder",
            "status": "done",
            "message": "优化提示词",
            "content": f"优化了 {len(optimized)} 个提示词\n" + "\n".join(f"  {i+1}. {p[:80]}" for i, p in enumerate(optimized)),
            "detail": {"step_count": len(optimized)},
        },
    ))

    updated_plan = dict(plan_dict) if isinstance(plan_dict, dict) else {}
    updated_steps = list(updated_plan.get("steps", []))
    for i, opt_prompt in enumerate(optimized):
        if i < len(updated_steps):
            if isinstance(updated_steps[i], dict):
                updated_steps[i] = dict(updated_steps[i])
                updated_steps[i]["prompt"] = opt_prompt
    updated_plan["steps"] = updated_steps

    return {
        "optimized_prompts": optimized,
        "execution_plan": updated_plan,
        "status": "prompts_ready",
    }
