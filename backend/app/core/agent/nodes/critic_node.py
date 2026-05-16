import json
import logging
import re

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.agent.state import AgentState
from app.core.agent.critic_interface import CriticOutput
from app.core.agent.capability_prompts import CRITIC_EVALUATION_DIMENSIONS
from app.core.agent.llm_call_logger import LLMCallRecord, extract_tokens, log_and_bill, LLMTimer
from app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

CRITIC_SYSTEM_PROMPT = (
    "You are an image quality critic. Analyze the given image and provide:\n\n"
    "1. A technical quality score from 0 to 10, where:\n"
    "   - 0-3: Severe defects (missing limbs, distorted faces, broken anatomy)\n"
    "   - 3-5: Noticeable issues (poor composition, blurry, artifacts)\n"
    "   - 5-7: Acceptable but could be improved\n"
    "   - 7-10: High quality, well-composed, detailed\n\n"
    f"{CRITIC_EVALUATION_DIMENSIONS}\n\n"
    "Output a JSON object with: "
    '"score" (float 0-10), '
    '"tags" (object with the 6 dimensions: style, color_temperature, composition, lighting, detail_level, mood), '
    '"issues" (array of specific, actionable Chinese strings). '
    "No markdown, no explanation outside the JSON."
)

MULTIMODAL_MODEL_PATTERNS = [
    "gpt-4", "gpt-4o", "gpt-4.", "gpt-5", "o3", "o4",
    "claude-", "gemini-", "gemini",
    "qwen", "internvl", "llava", "cogvlm",
]
MULTIMODAL_KEYWORD_PATTERNS = [
    r"vl\b", r"vision", r"visual", r"multimodal",
]


def _is_multimodal_model(model_id: str) -> bool:
    if not model_id:
        return False
    lower = model_id.lower()
    if any(p in lower for p in MULTIMODAL_MODEL_PATTERNS):
        return True
    import re as _re
    return any(_re.search(p, lower) for p in MULTIMODAL_KEYWORD_PATTERNS)


async def critic_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db = conf.get("db")

    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager
    _tm = conf.get("task_manager") or TaskManager()

    artifacts = state.get("artifacts", [])
    prompt = state.get("prompt", "")

    if not artifacts:
        return {"critic_results": [], "status": "critic_done"}

    llm_provider_id = state.get("llm_provider_id", "")
    if not db or not llm_provider_id:
        default_results = [
            CriticOutput(artifact_id=a.get("url", ""), score=7.0, tags={}, issues=[]).__dict__
            for a in artifacts if a.get("url")
        ]
        return {"critic_results": default_results, "status": "critic_done"}

    from app.models.api_provider import ApiProvider
    from app.services.generate_service import resolve_provider_vendor

    result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        default_results = [
            CriticOutput(artifact_id=a.get("url", ""), score=7.0, tags={}, issues=[]).__dict__
            for a in artifacts if a.get("url")
        ]
        return {"critic_results": default_results, "status": "critic_done"}

    is_known_multimodal = _is_multimodal_model(provider.model_id)
    if not is_known_multimodal:
        logger.info(
            f"critic_node: model {provider.model_id} not in known multimodal list, "
            f"will attempt multimodal call with fallback"
        )

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception:
        default_results = [
            CriticOutput(artifact_id=a.get("url", ""), score=7.0, tags={}, issues=[]).__dict__
            for a in artifacts if a.get("url")
        ]
        return {"critic_results": default_results, "status": "critic_done"}

    client = LLMClient(base_url=base_url, api_key=api_key, model_id=provider.model_id)

    critic_results: list[dict] = []
    multimodal_failed = False
    for artifact in artifacts:
        url = artifact.get("url", "")
        if not url:
            continue

        if multimodal_failed and not is_known_multimodal:
            logger.info(f"critic_node: skipping multimodal for {url[:50]} after earlier failure")
            critic_results.append(CriticOutput(
                artifact_id=url, score=7.0, tags={}, issues=[]
            ).__dict__)
            continue

        try:
            user_content = [
                {"type": "text", "text": f"Analyze this generated image. Original prompt: {prompt[:200]}"},
                {"type": "image_url", "image_url": {"url": url, "detail": "auto"}},
            ]
            messages = [
                {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            with LLMTimer() as timer:
                full_text = ""
                usage_data = None
                async for delta, usage in client.chat_stream(messages, temperature=0.3):
                    full_text += delta
                    await _tm.publish(LamEvent(
                        event_type="task_progress",
                        correlation_id=f"agent-{state.get('session_id', '')}",
                        payload={
                            "type": "agent_token",
                            "session_id": state.get("session_id", ""),
                            "node": "critic",
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
                    node="critic",
                    model_id=provider.model_id,
                    provider_id=llm_provider_id,
                    session_id=state.get("session_id", ""),
                    tokens_in=t_in,
                    tokens_out=t_out,
                    latency_ms=timer.ms,
                    billing_type="agent",
                    system_prompt=CRITIC_SYSTEM_PROMPT,
                    user_content=json.dumps(user_content, ensure_ascii=False),
                    response_text=text,
                    extra={"artifact_index": artifacts.index(artifact)},
                ))
            text = text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            parsed = json.loads(text)
            if isinstance(parsed, dict):
                score = float(parsed.get("score", 7.0))
                score = max(0.0, min(10.0, score))
                tags = parsed.get("tags", {})
                issues = parsed.get("issues", [])
                if not isinstance(issues, list):
                    issues = []
                if not isinstance(tags, dict):
                    tags = {}

                critic_results.append(CriticOutput(
                    artifact_id=url,
                    score=score,
                    tags=tags,
                    issues=[str(i) for i in issues],
                ).__dict__)
            else:
                critic_results.append(CriticOutput(
                    artifact_id=url, score=7.0, tags={}, issues=[]
                ).__dict__)
        except Exception as e:
            logger.warning(f"critic_node: analysis failed for {url[:50]}: {e}")
            if not is_known_multimodal:
                multimodal_failed = True
                logger.info("critic_node: model likely not multimodal, will skip remaining artifacts")
            critic_results.append(CriticOutput(
                artifact_id=url, score=7.0, tags={}, issues=[]
            ).__dict__)

    avg_score = sum(r.get("score", 7.0) for r in critic_results) / len(critic_results) if critic_results else 7.0
    logger.info(f"critic_node: analyzed {len(critic_results)} artifacts, avg_score={avg_score:.1f}")

    score_lines = []
    for i, r in enumerate(critic_results):
        score = r.get("score", 7.0)
        issues = r.get("issues", [])
        issue_str = ", ".join(str(x) for x in issues[:3]) if issues else ""
        score_lines.append(f"  #{i+1}: {score:.1f}" + (f" ({issue_str})" if issue_str else ""))
    content = f"平均 {avg_score:.1f} 分, {len(critic_results)} 张图已评估\n" + "\n".join(score_lines)

    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{state.get('session_id', '')}",
        payload={
            "type": "agent_node_progress",
            "session_id": state.get("session_id", ""),
            "node": "critic",
            "status": "done",
            "message": "评估结果",
            "content": content,
            "detail": {"avg_score": round(avg_score, 1), "artifact_count": len(critic_results)},
        },
    ))

    return {"critic_results": critic_results, "status": "critic_done"}
