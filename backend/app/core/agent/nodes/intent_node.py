import logging

from langchain_core.runnables import RunnableConfig

from app.core.agent.state import AgentState
from app.core.agent.capability_prompts import STRATEGY_EXECUTION_MECHANISM, IMAGE_SYSTEM_CONSTRAINTS
from app.core.agent.llm_call_logger import LLMCallRecord, extract_tokens, log_and_bill, LLMTimer
from app.services.agent_intent_service import STRATEGY_MAP, classify_intent_with_llm

logger = logging.getLogger(__name__)

INTENT_NODE_SYSTEM_PROMPT = (
    "You are a task classifier for an AI image generation agent. "
    "Given the user's request, classify it into exactly one of these task types "
    "and determine whether web search would help produce better results.\n\n"
    f"{STRATEGY_EXECUTION_MECHANISM}\n"
    f"{IMAGE_SYSTEM_CONSTRAINTS}\n"
    "## Classification Task\n\n"
    "Classify the user's request into one of:\n\n"
    "1. **radiate** — SIBLING outputs. The user wants a COMPLETE SET where each "
    "member is equally important and indispensable. The final deliverable is the "
    "whole collection, not any single item. "
    "Examples: 三视图(正面/侧面/背面), 表情包套图, 图标集, 同角色不同姿势, 系列插画.\n\n"
    "2. **iterative** — ANCESTOR outputs. The user wants a REFINEMENT CHAIN where "
    "each step produces a BETTER version of the previous one. The final deliverable "
    "is the LAST image; intermediate steps are scaffolding. "
    "Examples: 先画草图再精修, 先出线稿再上色最后加光影, based on previous, continue to improve.\n\n"
    "3. **multi_independent** — UNRELATED outputs. The user wants MULTIPLE DISTINCT "
    "results that have NO dependency or relationship to each other. "
    "Examples: 3张不同风格的猫, 分别画logo方案1和方案2, different designs.\n\n"
    "4. **single** — ONE output. Simple request, single image, or variants of the same prompt. Default.\n\n"
    "## Decision Rules — determine the RELATIONSHIP between outputs:\n\n"
    "- If all members form a complete, equally-important SET → radiate\n"
    "  (三视图, 表情包, 图标集, 系列, same character different poses/angles)\n"
    "- If later outputs are BETTER versions of earlier ones → iterative\n"
    "  (sketch→refine, draft→polish, step-by-step improvement)\n"
    "- If outputs have NO relationship to each other → multi_independent\n"
    "  (different styles, different designs, unrelated concepts)\n"
    "- If only ONE output matters → single (default)\n\n"
    '## Key disambiguation:\n'
    '- "三视图 猫" → siblings (front/side/back together define the character) → radiate\n'
    '- "3张不同风格的猫" → unrelated (each stands alone) → multi_independent\n'
    '- "先画草图再精修" → ancestor (final refined version is the goal) → iterative\n'
    '- "画一只猫" → single\n\n'
    "## Search Intent\n\n"
    "Determine whether searching the web for reference material would significantly "
    "improve the image generation result. Set `needs_search` to true when:\n"
    "- The user explicitly asks for references, trends, or latest styles (参考/搜索/趋势/流行/最新)\n"
    "- The subject is specific enough that real-world references would help "
    "(e.g. a particular animal breed, architectural style, historical costume, brand design)\n"
    "- The request involves unfamiliar or niche visual domains "
    "(e.g. cyberpunk fashion, biomechanical art, specific cultural motifs)\n"
    "- The user wants to match a current trend or popular aesthetic\n\n"
    "Set `needs_search` to false when:\n"
    "- The request is simple and generic (e.g. 'a cute cat', 'a sunset landscape')\n"
    "- The user provides enough visual context via reference images\n"
    "- The subject is common knowledge that doesn't need research\n\n"
    "Output a JSON object with: "
    '"task_type" (one of: radiate/iterative/multi_independent/single), '
    '"expected_count" (integer, number of final images), '
    '"confidence" (float 0.0-1.0), '
    '"needs_search" (boolean, whether web search would help), '
    '"items" (array of {label, prompt_hint} objects, only for multi_independent/radiate), '
    '"references" (array of strings, explicit image references), '
    '"reason" (brief Chinese explanation). '
    "No markdown, no explanation outside the JSON."
)


async def intent_node(state: AgentState, config: RunnableConfig) -> dict:
    existing = state.get("intent")
    if existing and isinstance(existing, dict) and existing.get("task_type") and existing.get("confidence", 0) >= 0.1:
        logger.info(f"intent_node: intent already parsed (task_type={existing.get('task_type')}), skipping")
        return {}

    conf = config.get("configurable", {})
    db = conf.get("db")

    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager
    _tm = conf.get("task_manager") or TaskManager()

    prompt = state.get("prompt", "")
    image_count = state.get("image_count", 1)
    context_images = state.get("context_images", []) or None
    session_id = state.get("session_id", "")

    llm_api_key = ""
    llm_base_url = ""
    llm_model_id = ""
    llm_provider_id = state.get("llm_provider_id", "")

    if db and llm_provider_id:
        from sqlalchemy import select
        from app.models.api_provider import ApiProvider
        from app.services.generate_service import resolve_provider_vendor

        result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
        provider = result.scalar_one_or_none()
        if provider:
            try:
                llm_base_url, llm_api_key = await resolve_provider_vendor(db, provider)
                llm_model_id = provider.model_id
            except Exception:
                pass

    if not llm_api_key:
        logger.info("intent_node: no LLM API key available, defaulting to single")
        await _tm.publish(LamEvent(
            event_type="task_progress",
            correlation_id=f"agent-{session_id}",
            payload={
                "type": "agent_node_progress",
                "session_id": session_id,
                "node": "intent",
                "status": "done",
                "message": "解析意图",
                "content": "分类: single, 置信度 0.3。无 LLM key",
                "detail": {"task_type": "single", "strategy": "single", "confidence": 0.3},
            },
        ))
        return {
            "intent": {
                "task_type": "single",
                "expected_count": image_count,
                "strategy": "single",
                "items": [],
                "references": [],
                "confidence": 0.3,
                "needs_search": False,
                "reason": "no LLM key, defaulting to single",
            },
            "needs_search": False,
            "status": "intent_parsed",
        }

    with LLMTimer() as timer:
        llm_result, billing_info = await classify_intent_with_llm(
            prompt=prompt,
            image_count=image_count,
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model_id=llm_model_id,
            context_images=context_images,
            task_manager=_tm,
            session_id=session_id,
        )

    if db and llm_provider_id:
        await log_and_bill(db, LLMCallRecord(
            node="intent",
            model_id=llm_model_id,
            provider_id=llm_provider_id,
            session_id=session_id,
            tokens_in=billing_info.get("tokens_in", 0),
            tokens_out=billing_info.get("tokens_out", 0),
            latency_ms=timer.ms,
            billing_type="agent",
            system_prompt=billing_info.get("system_prompt", ""),
            user_content=billing_info.get("user_content", ""),
            response_text=billing_info.get("response_text", ""),
        ))

    if llm_result is None:
        logger.warning("intent_node: LLM classification failed, defaulting to single")
        await _tm.publish(LamEvent(
            event_type="task_progress",
            correlation_id=f"agent-{session_id}",
            payload={
                "type": "agent_node_progress",
                "session_id": session_id,
                "node": "intent",
                "status": "done",
                "message": "解析意图",
                "content": "分类: single, 置信度 0.3。LLM 分类失败",
                "detail": {"task_type": "single", "strategy": "single", "confidence": 0.3},
            },
        ))
        return {
            "intent": {
                "task_type": "single",
                "expected_count": image_count,
                "strategy": "single",
                "items": [],
                "references": [],
                "confidence": 0.3,
                "needs_search": False,
                "reason": "LLM classification failed, defaulting to single",
            },
            "needs_search": False,
            "status": "intent_parsed",
        }

    task_type = llm_result.get("task_type", "single")
    strategy = STRATEGY_MAP.get(task_type, "single")
    expected_count = llm_result.get("expected_count", image_count)
    confidence = llm_result.get("confidence", 0.5)
    items = llm_result.get("items", [])
    references = llm_result.get("references", [])
    reason = llm_result.get("reason", "")
    needs_search = bool(llm_result.get("needs_search", False))

    intent_dict = {
        "task_type": task_type,
        "expected_count": expected_count,
        "strategy": strategy,
        "items": items,
        "references": references,
        "confidence": confidence,
        "user_goal": prompt,
        "reason": reason,
        "needs_search": needs_search,
        "decision_trace": {
            "source": "llm",
            "llm_task_type": task_type,
            "llm_confidence": confidence,
            "llm_reason": reason,
            "llm_needs_search": needs_search,
            "final_task_type": task_type,
            "final_confidence": confidence,
        },
    }

    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{session_id}",
        payload={
            "type": "agent_node_progress",
            "session_id": session_id,
            "node": "intent",
            "status": "done",
            "message": "解析意图",
            "content": f"分类: {task_type}, 置信度 {confidence:.2f}。{reason}",
            "detail": {"task_type": task_type, "strategy": strategy, "confidence": confidence, "reason": reason},
        },
    ))

    logger.info(
        f"intent_node: task_type={task_type}, strategy={strategy}, "
        f"confidence={confidence:.2f}, expected_count={expected_count}, "
        f"items={len(items)}, reason={reason[:60]}"
    )

    return {
        "intent": intent_dict,
        "needs_search": needs_search,
        "status": "intent_parsed",
    }
