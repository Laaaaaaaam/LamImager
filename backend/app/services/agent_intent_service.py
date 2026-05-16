import json
import logging
import re
from dataclasses import dataclass, field

from app.utils.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AgentItem:
    id: str
    label: str
    prompt_hint: str
    role: str = "final"
    reference_urls: list[str] | None = None


@dataclass
class AgentIntent:
    task_type: str
    expected_count: int
    strategy: str = "single"
    items: list[AgentItem] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    reference_images: list[str] = field(default_factory=list)
    reference_labels: list[dict] = field(default_factory=list)
    requires_consistency: bool = False
    confidence: float = 0.0
    needs_search: bool = False
    user_goal: str = ""
    reason: str = ""
    decision_trace: dict = field(default_factory=dict)


STRATEGY_MAP: dict[str, str] = {
    "single": "single",
    "multi_independent": "parallel",
    "iterative": "iterative",
    "radiate": "radiate",
}

TASK_TYPE_LABELS: dict[str, str] = {
    "single": "单图生成",
    "multi_independent": "多图并行",
    "iterative": "迭代精修",
    "radiate": "套图辐射",
}

PROMPT_HINT_MAP: dict[str, str] = {
    "正面": "front view",
    "侧面": "side view",
    "背面": "back view",
    "左": "left side",
    "右": "right side",
    "上": "top view",
    "下": "bottom view",
    "前": "front",
    "后": "back",
    "开心": "happy expression",
    "生气": "angry expression",
    "惊讶": "surprised expression",
    "哭": "crying expression",
    "笑": "laughing expression",
    "害羞": "shy expression",
    "酷": "cool expression",
    "正常": "neutral expression",
    "front": "front view",
    "side": "side view",
    "back": "back view",
    "happy": "happy expression",
    "angry": "angry expression",
    "surprised": "surprised expression",
    "crying": "crying expression",
    "laughing": "laughing expression",
    "shy": "shy expression",
    "cool": "cool expression",
    "neutral": "neutral expression",
    "sad": "sad expression",
    "excited": "excited expression",
}


def has_search_intent(prompt: str) -> bool:
    lower = prompt.lower()
    search_keywords = r"(参考|搜索|搜寻|查找|找|趋势|流行|最新|热门|参考图|参考资料|reference|search|trend|popular|latest|look\s+up|find)"
    return bool(re.search(search_keywords, lower))


async def resolve_context_references(
    db=None,
    session_id: str = "",
    prompt: str = "",
    context_messages: list[dict] | None = None,
    reference_labels: list[dict] | None = None,
) -> list[str]:
    urls: list[str] = []

    tag_matches = re.findall(r"\[图\d+\]", prompt)
    if tag_matches and reference_labels:
        label_map: dict[str, str] = {}
        for lbl in reference_labels:
            if isinstance(lbl, dict):
                label_map[lbl.get("label", "")] = lbl.get("url", "")
        for tag in tag_matches:
            if tag in label_map and label_map[tag]:
                urls.append(label_map[tag])

    if context_messages:
        for msg in context_messages:
            if isinstance(msg, dict):
                img_urls = msg.get("image_urls", [])
                if img_urls:
                    urls.extend(img_urls)

    if not urls and db and session_id:
        try:
            from sqlalchemy import select, or_
            from app.models.message import Message, MessageRole, MessageType

            result = await db.execute(
                select(Message)
                .where(
                    Message.session_id == session_id,
                    Message.role == MessageRole.assistant,
                    or_(
                        Message.message_type == MessageType.image,
                        Message.message_type == "agent",
                    ),
                )
                .order_by(Message.created_at.desc())
                .limit(4)
            )
            recent = result.scalars().all()
            for msg in recent:
                meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
                if msg.message_type == "agent":
                    img_urls = meta.get("images", [])
                else:
                    img_urls = meta.get("image_urls", [])
                if img_urls:
                    urls.extend(img_urls)
        except Exception:
            pass

    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def validate_agent_result(intent: AgentIntent, result: dict) -> bool:
    if intent.task_type == "multi_independent":
        expected = intent.expected_count
        actual = len(result.get("final_images", []))
        return actual >= expected

    if intent.task_type == "single":
        actual = len(result.get("images", []))
        return actual >= intent.expected_count if intent.expected_count > 1 else actual >= 1

    return True


def _extract_tokens_from_response(response: dict) -> tuple[int, int]:
    usage = response.get("usage", {})
    if isinstance(usage, dict):
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    return 0, 0


def _build_multimodal_user_content(text: str, image_urls: list[str] | None) -> str | list[dict]:
    if not image_urls:
        return text
    parts: list[dict] = [{"type": "text", "text": text}]
    for idx, img_url in enumerate(image_urls[:2]):
        parts.append({
            "type": "image_url",
            "image_url": {"url": img_url, "detail": "auto"},
        })
    return parts


INTENT_CLASSIFIER_PROMPT = (
    "You are a task classifier for an AI image generation agent. "
    "Given the user's request, classify it into exactly one of these types "
    "and determine whether web search would help produce better results.\n\n"
    "1. **radiate** — User wants a SET of images with UNIFIED style/theme/character "
    "(e.g. sticker pack, emoji set, series, icon set, same character in different poses). "
    "Keywords: 套图/一组/系列/表情包/同角色/同风格/图标集.\n\n"
    "2. **iterative** — User wants STEP-BY-STEP refinement, where each step builds on the previous "
    "(e.g. rough draft then polish, sketch then refine, improve based on previous result). "
    "Keywords: 先...再.../草图精修/基于上一张/继续改.\n\n"
    "3. **multi_independent** — User wants MULTIPLE INDEPENDENT variations with DIFFERENT styles/approaches "
    "OR multiple views (front/side/back) OR explicitly different designs. "
    "Keywords: 不同风格/三视图/多个方案/分别画/N张不同.\n\n"
    "4. **single** — User wants ONE image or multiple images with the SAME prompt/style. "
    "This is the default for simple requests.\n\n"
    "Decision rules:\n"
    "- If the user explicitly requests DIFFERENT styles/approaches → multi_independent\n"
    "- If the user wants multiple images of the SAME character/style → radiate\n"
    "- If the request has sequential steps (first X then Y) → iterative\n"
    "- If the request is about refining/modifying a previous image → single\n"
    "- Default → single\n\n"
    "## Search Intent\n\n"
    "Determine whether searching the web for reference material would significantly "
    "improve the image generation result. Set `needs_search` to true when:\n"
    "- The user explicitly asks for references, trends, or latest styles\n"
    "- The subject is specific enough that real-world references would help\n"
    "- The request involves unfamiliar or niche visual domains\n"
    "- The user wants to match a current trend or popular aesthetic\n\n"
    "Set `needs_search` to false when:\n"
    "- The request is simple and generic\n"
    "- The user provides enough visual context via reference images\n"
    "- The subject is common knowledge that doesn't need research\n\n"
    "Output a JSON object with: "
    '"task_type" (one of: radiate/iterative/multi_independent/single), '
    '"expected_count" (integer, number of final images), '
    '"confidence" (float 0.0-1.0, how sure you are), '
    '"needs_search" (boolean, whether web search would help), '
    '"items" (array of objects with "label" and "prompt_hint" strings, only for multi_independent/radiate), '
    '"references" (array of strings, any explicit image references like [图1] URLs), '
    '"reason" (brief Chinese explanation). '
    "No markdown, no explanation outside the JSON."
)


async def classify_intent_with_llm(
    prompt: str,
    image_count: int,
    llm_api_key: str,
    llm_base_url: str = "",
    llm_model_id: str = "",
    context_images: list[str] | None = None,
    task_manager=None,
    session_id: str = "",
) -> tuple[dict | None, dict]:
    billing_info: dict = {"tokens_in": 0, "tokens_out": 0}
    logger.info(
        f"classify_intent_with_llm: calling LLM, model_id={llm_model_id}, "
        f"prompt={prompt[:60]}..., context_images={len(context_images) if context_images else 0}"
    )
    user_msg = json.dumps({"request": prompt, "explicit_count": image_count}, ensure_ascii=False)

    try:
        client = LLMClient(base_url=llm_base_url, api_key=llm_api_key, model_id=llm_model_id)
        user_content = _build_multimodal_user_content(user_msg, context_images)
        messages = [
            {"role": "system", "content": INTENT_CLASSIFIER_PROMPT},
            {"role": "user", "content": user_content},
        ]
        full_text = ""
        usage_data = None
        async for delta, usage in client.chat_stream(messages, temperature=0.3):
            full_text += delta
            if task_manager:
                from app.core.events import LamEvent
                await task_manager.publish(LamEvent(
                    event_type="task_progress",
                    correlation_id=f"agent-{session_id}",
                    payload={
                        "type": "agent_token",
                        "session_id": session_id,
                        "node": "intent",
                        "content": delta,
                    },
                ))
            if usage:
                usage_data = usage
        t_in = usage_data.get("prompt_tokens", 0) if usage_data else 0
        t_out = usage_data.get("completion_tokens", 0) if usage_data else 0
        billing_info["tokens_in"] = t_in
        billing_info["tokens_out"] = t_out
        text = full_text
        billing_info["system_prompt"] = INTENT_CLASSIFIER_PROMPT
        billing_info["user_content"] = json.dumps(user_content, ensure_ascii=False) if isinstance(user_content, list) else str(user_content)
        billing_info["response_text"] = text
        logger.debug(f"classify_intent_with_llm: raw response = {text[:200]}")
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("task_type") in ("radiate", "iterative", "multi_independent", "single"):
            parsed.setdefault("expected_count", image_count)
            parsed.setdefault("confidence", 0.5)
            parsed.setdefault("needs_search", False)
            parsed.setdefault("reason", "")
            parsed.setdefault("items", [])
            parsed.setdefault("references", [])
            logger.info(
                f"classify_intent_with_llm: parsed result = {parsed.get('task_type')}, "
                f"confidence={parsed.get('confidence')}, reason={parsed.get('reason', '')[:50]}"
            )
            return parsed, billing_info
        else:
            logger.warning(f"classify_intent_with_llm: invalid task_type in response: {parsed.get('task_type')}")
    except Exception as e:
        logger.warning(f"classify_intent_with_llm failed: {e}")
    return None, billing_info
