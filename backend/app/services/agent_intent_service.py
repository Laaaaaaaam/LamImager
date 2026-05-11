from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.utils.llm_client import LLMClient
from app.services.task_manager import TaskStatus

logger = logging.getLogger(__name__)


# === Design Constraints for Planner / Prompt Builder ===
#
# 1. 规划阶段（_generate_iterative_steps / _generate_radiate_params /
#    _generate_item_prompts）支持 context images 多模态推理，
#    以提升步骤与子项 prompt 质量。
#
# 2. 图片参考优先级规则（Planner 执行时生效）：
#    用户上传图 / 上下文图 > 用户文本目标 > 搜索结果
#    搜索结果仅作补充，不得覆盖视觉事实。
#
# 3. 后续收敛方向：统一 PlanningContext(prompt, context_images,
#    reference_images, search_context, intent, expected_count)。


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
    user_goal: str = ""


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


def _extract_item_labels(text: str, prefix_pattern: str) -> list[str]:
    stripped = re.sub(prefix_pattern, "", text, count=1, flags=re.IGNORECASE).strip()
    items: list[str] = []
    if "，" in stripped or "," in stripped:
        parts = re.split(r"[，,、;；]", stripped)
    else:
        parts = [stripped]
    for p in parts:
        p = p.strip()
        p = re.sub(r"^and\s+", "", p, flags=re.IGNORECASE)
        p = re.sub(r"^\d+[\.\、\)）]\s*", "", p)
        if p and len(p) <= 20:
            items.append(p)
    return items


def _has_different_style_keyword(text: str) -> bool:
    return bool(re.search(r"不同风格|不同.*风格|variants?|different\s+style|不同方案|多个方案|不同logo|不同设计", text.lower()))


def _has_consistency_keyword(text: str) -> bool:
    lower = text.lower()
    if re.search(r"统一风格|风格统一|风格一致|consistent\s+style|same\s+style", lower):
        if not _has_different_style_keyword(text):
            return True
    if re.search(r"(?<!不)同风格", lower):
        return True
    return False


def _count_n_images(text: str) -> int | None:
    cm = re.search(r"(\d+)\s*[张張個个套组]|(\d+)\s*images?", text)
    if cm:
        return int(cm.group(1) or cm.group(2))
    return None


def has_search_intent(prompt: str) -> bool:
    lower = prompt.lower()
    search_keywords = r"(参考|搜索|搜寻|查找|找|趋势|流行|最新|热门|参考图|参考资料|reference|search|trend|popular|latest|look\s+up|find)"
    return bool(re.search(search_keywords, lower))


def parse_agent_intent(
    prompt: str,
    image_count: int = 1,
    context_messages: list[dict] | None = None,
    reference_labels: list[dict] | None = None,
) -> AgentIntent:
    lower = prompt.lower()

    def _make_intent(
        task_type: str,
        expected_count: int = 1,
        items: list[AgentItem] | None = None,
        confidence: float = 1.0,
    ) -> AgentIntent:
        strategy = STRATEGY_MAP.get(task_type, "single")
        intent = AgentIntent(
            task_type=task_type,
            expected_count=expected_count,
            strategy=strategy,
            items=items or [],
            user_goal=prompt,
            confidence=confidence,
        )
        intent.requires_consistency = _requires_consistency(intent)
        return intent

    # ── Priority 1: radiate ──────────────────────────────────────────
    # 套图/一组/系列/一套/set/series/collection/pack
    radiate_pattern = r"(套图|一组|系列|一套|set\b|series|collection|pack\b)"
    if re.search(radiate_pattern, lower) and not _has_different_style_keyword(prompt):
        count_n = _count_n_images(prompt) or 2
        return _make_intent("radiate", expected_count=count_n, confidence=1.0)

    # 统一风格/同风格/consistent/same style (排除"不同风格")
    if _has_consistency_keyword(prompt):
        count_n = _count_n_images(prompt) or image_count
        if count_n >= 2:
            return _make_intent("radiate", expected_count=count_n, confidence=1.0)

    # 同一角色/同角色/same character
    same_char = r"(同一角色|同角色|same\s+character|同一个角色)"
    if re.search(same_char, lower):
        count_n = _count_n_images(prompt) or image_count
        if count_n >= 2:
            return _make_intent("radiate", expected_count=count_n, confidence=1.0)
        return _make_intent("radiate", expected_count=max(count_n, 2), confidence=0.85)

    # 表情包/贴纸包/sticker pack (without "不同风格") → radiate
    sticker_pattern = r"(表情包|贴纸包|sticker\s*pack|emoticon\s*set|meme\s*set|图标集|icon\s*set|四联画|成组|插画集)"
    sticker_m = re.search(sticker_pattern, lower)
    if sticker_m and not _has_different_style_keyword(prompt):
        count_n = _count_n_images(prompt)
        if count_n and count_n >= 2:
            return _make_intent("radiate", expected_count=count_n, confidence=1.0)
        labels = _extract_item_labels(prompt, sticker_m.group(0))
        if labels and len(labels) >= 2:
            items = [
                AgentItem(id=f"item_{i}", label=label, prompt_hint=PROMPT_HINT_MAP.get(label, label))
                for i, label in enumerate(labels)
            ]
            return _make_intent("radiate", expected_count=len(items), items=items, confidence=0.85)
        return _make_intent("radiate", expected_count=4, confidence=0.7)

    # N张 + (同风格/统一/同角色/一套) → radiate (排除"不同风格")
    n_img = _count_n_images(prompt)
    if n_img and n_img >= 2 and not _has_different_style_keyword(prompt):
        radiate_context = r"(同风格|统一|同角色|一套|同系列|same|consistent|unified)"
        if re.search(radiate_context, lower):
            return _make_intent("radiate", expected_count=n_img, confidence=0.85)

    # ── Priority 2: iterative ────────────────────────────────────────
    # 先...再...最后... / first...then...finally
    iterative_pattern = r"(先|首先|first)\s*.*(再|然后|接着|then|next)\s*.*(最后|finally)"
    if re.search(iterative_pattern, lower):
        count_m = re.search(r"(\d+)\s*步", prompt)
        n = int(count_m.group(1)) if count_m else 2
        return _make_intent("iterative", expected_count=n, confidence=1.0)

    # 先...再... (2-step without "最后")
    iterative_2step = r"(先|首先|first)\s*.{2,}(再|然后|接着|then|next)"
    if re.search(iterative_2step, lower):
        return _make_intent("iterative", expected_count=2, confidence=1.0)

    # 草图.*精修 / sketch.*refine
    if re.search(r"草图.*精修|sketch.*refine|初稿.*精修|draft.*refine", lower):
        return _make_intent("iterative", expected_count=2, confidence=1.0)

    # 基于上一张/继续改/延续上一步
    if re.search(r"基于上一张|继续改|延续上一步|基于.*上一步|基于.*上一张|refine.*previous|based\s+on.*previous", lower):
        return _make_intent("iterative", expected_count=2, confidence=1.0)

    # ── Priority 3: multi_independent ────────────────────────────────
    # 三视图 + direction enumeration
    threesight_zh = re.search(r"三视图", prompt)
    threesight_en = re.search(r"three\s*views?", lower)
    has_front = re.search(r"正面|front", lower)
    has_side = re.search(r"侧面|side", lower)
    has_back = re.search(r"背面|back", lower)
    if (threesight_zh or threesight_en) and sum([bool(has_front), bool(has_side), bool(has_back)]) >= 2:
        is_chinese = bool(threesight_zh) or bool(re.search(r"[\u4e00-\u9fff]", prompt))
        items = [
            AgentItem(id="front", label="正面" if is_chinese else "front", prompt_hint=PROMPT_HINT_MAP.get("正面", "front view")),
            AgentItem(id="side", label="侧面" if is_chinese else "side", prompt_hint=PROMPT_HINT_MAP.get("侧面", "side view")),
            AgentItem(id="back", label="背面" if is_chinese else "back", prompt_hint=PROMPT_HINT_MAP.get("背面", "back view")),
        ]
        return _make_intent("multi_independent", expected_count=3, items=items, confidence=1.0)

    # Bare direction enumeration (no sheet/turnaround)
    sheet_keywords = r"sheet|turnaround|设定表|排版|一张图|单张"
    has_sheet = re.search(sheet_keywords, lower)
    if not has_sheet:
        dir_zh = re.findall(r"(正面|侧面|背面|前面|后面|左边|右边|上面|下面)", prompt)
        if len(dir_zh) >= 2:
            unique_dirs = list(dict.fromkeys(dir_zh))
            items = []
            for i, d in enumerate(unique_dirs):
                did = d if d in ("正面", "侧面", "背面", "左", "右", "上", "下", "前", "后") else f"item_{i}"
                items.append(AgentItem(id=did, label=d, prompt_hint=PROMPT_HINT_MAP.get(d, d)))
            return _make_intent("multi_independent", expected_count=len(items), items=items, confidence=0.85)
        dir_en = re.findall(r"\b(front|side|back|left|right|top|bottom)\b", lower)
        if len(dir_en) >= 2:
            unique_dirs = list(dict.fromkeys(dir_en))
            items = []
            for d in unique_dirs:
                hint = PROMPT_HINT_MAP.get(d, f"{d} view")
                items.append(AgentItem(id=d, label=d, prompt_hint=hint))
            return _make_intent("multi_independent", expected_count=len(items), items=items, confidence=0.85)

    # N张不同风格/N个方案/分别画/每张不同
    if _has_different_style_keyword(prompt):
        count_n = _count_n_images(prompt) or image_count
        if count_n >= 2:
            auto_items = [
                AgentItem(id=f"style_{i+1}", label=f"风格{i+1}", prompt_hint=f"style variation {i+1}")
                for i in range(count_n)
            ]
            return _make_intent("multi_independent", expected_count=count_n, items=auto_items, confidence=1.0)

    if re.search(r"分别画|每张不同|多个方案|不同方案|不同logo|不同设计|different\s+approach|different\s+logo", lower):
        count_n = _count_n_images(prompt) or image_count
        if count_n >= 2:
            auto_items = [
                AgentItem(id=f"variant_{i+1}", label=f"方案{i+1}", prompt_hint=f"design variation {i+1}")
                for i in range(count_n)
            ]
            return _make_intent("multi_independent", expected_count=count_n, items=auto_items, confidence=0.85)
        auto_items = [
            AgentItem(id=f"variant_{i+1}", label=f"方案{i+1}", prompt_hint=f"design variation {i+1}")
            for i in range(max(image_count, 2))
        ]
        return _make_intent("multi_independent", expected_count=max(image_count, 2), items=auto_items, confidence=0.7)

    # N张 + list enumeration (without radiate keywords)
    count_pattern_en = re.search(r"(\d+)\s*images", lower)
    count_pattern_zh = re.search(r"(\d+)\s*[张張個个]", prompt)
    count_m = count_pattern_en or count_pattern_zh
    if count_m:
        n = int(count_m.group(1))
        prompt_after = prompt[count_m.end():].strip()
        has_list = bool(re.search(r"[，,、;；]", prompt_after)) or bool(re.search(r"^\d+[\.\、\)）]", prompt_after))
        if n >= 2 and has_list:
            prefix = count_m.group(0)
            labels = _extract_item_labels(prompt, prefix)
            if labels:
                items = [
                    AgentItem(id=f"item_{i}", label=label, prompt_hint=PROMPT_HINT_MAP.get(label, label))
                    for i, label in enumerate(labels)
                ]
                return _make_intent("multi_independent", expected_count=len(items), items=items, confidence=0.85)

    # ── Priority 4: single (default) ─────────────────────────────────
    # Special: 三视图 + sheet keyword → single (1 image)
    if re.search(r"三视图|three\s*views?", lower):
        sheet_kw = r"(设定表|sheet|turnaround|一张图|排版|参考图)"
        if re.search(sheet_kw, lower):
            return _make_intent("single", expected_count=1, confidence=0.9)

    # 变体/多张同风格/image_count > 1
    variant_keywords = r"(同一提示词|同一个.*prompt|不同风格|variants?|版本|变体)"
    if re.search(variant_keywords, lower) or image_count > 1:
        count_m2 = re.search(r"(\d+)\s*[张張個个]", prompt)
        n = int(count_m2.group(1)) if count_m2 else image_count
        return _make_intent("single", expected_count=n, confidence=0.7)

    # 显式单图关键词 → 高置信单图
    if re.search(r"画一张|一张图|一个.*图|生成一张|generate\s+a\s+single|one\s+image", lower):
        return _make_intent("single", expected_count=max(image_count, 1), confidence=0.9)

    # Default fallback — low confidence, may be anything
    return _make_intent("single", expected_count=max(image_count, 1), confidence=0.3)


def _requires_consistency(intent: AgentIntent) -> bool:
    if intent.task_type in ("multi_independent", "radiate", "iterative"):
        return True
    lower = intent.user_goal.lower()
    consistency_keywords = r"(同一角色|同一个|character|consistent|same style|统一风格)"
    if re.search(consistency_keywords, lower):
        return True
    return False


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
            from sqlalchemy import select
            from app.models.message import Message, MessageRole, MessageType

            result = await db.execute(
                select(Message)
                .where(
                    Message.session_id == session_id,
                    Message.role == MessageRole.assistant,
                    Message.message_type == MessageType.image,
                )
                .order_by(Message.created_at.desc())
                .limit(4)
            )
            recent = result.scalars().all()
            for msg in recent:
                meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
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


# === LLM Intent Classifier (hybrid fallback) ===

INTENT_CLASSIFIER_PROMPT = (
    "You are a task classifier for an AI image generation agent. "
    "Given the user's request, classify it into exactly one of these types:\n\n"
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
    "Output a JSON object with: "
    '"task_type" (one of: radiate/iterative/multi_independent/single), '
    '"expected_count" (integer, number of final images), '
    '"confidence" (float 0.0-1.0, how sure you are), '
    '"reason" (brief Chinese explanation). '
    "No markdown, no explanation outside the JSON."
)


async def _classify_intent_with_llm(
    prompt: str,
    image_count: int,
    llm_api_key: str,
    llm_base_url: str = "",
    llm_model_id: str = "",
    context_images: list[str] | None = None,
) -> dict | None:
    user_msg = json.dumps({"request": prompt, "explicit_count": image_count}, ensure_ascii=False)

    try:
        client = LLMClient(base_url=llm_base_url, api_key=llm_api_key, model_id=llm_model_id)
        user_content = _build_multimodal_user_content(user_msg, context_images)
        result = await client.chat(
            messages=[
                {"role": "system", "content": INTENT_CLASSIFIER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
        )
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        if isinstance(parsed, dict) and parsed.get("task_type") in ("radiate", "iterative", "multi_independent", "single"):
            parsed.setdefault("expected_count", image_count)
            parsed.setdefault("confidence", 0.5)
            parsed.setdefault("reason", "")
            return parsed
    except Exception as e:
        logger.warning(f"_classify_intent_with_llm failed: {e}")
    return None


# === Intent Decision Policy ===

HYBRID_CONFIDENCE_THRESHOLD = 0.8

def _pick_best_intent(regex_intent: AgentIntent, llm_result: dict | None) -> AgentIntent:
    if llm_result is None:
        return regex_intent

    llm_type = llm_result["task_type"]
    llm_confidence = llm_result.get("confidence", 0.5)
    llm_count = llm_result.get("expected_count", 1)
    llm_reason = llm_result.get("reason", "")

    logger.info(
        f"Hybrid intent: regex=({regex_intent.task_type}, c={regex_intent.confidence:.2f}), "
        f"llm=({llm_type}, c={llm_confidence:.2f}) reason={llm_reason[:80]}"
    )

    if llm_type == regex_intent.task_type:
        regex_intent.confidence = max(regex_intent.confidence, llm_confidence)
        regex_intent.expected_count = max(regex_intent.expected_count, llm_count)
        return regex_intent

    if llm_confidence > regex_intent.confidence + 0.2:
        logger.info(f"LLM overrides regex: {regex_intent.task_type} → {llm_type}")
        strategy = STRATEGY_MAP.get(llm_type, "single")
        return AgentIntent(
            task_type=llm_type,
            expected_count=llm_count,
            strategy=strategy,
            items=regex_intent.items,
            references=regex_intent.references,
            reference_images=regex_intent.reference_images,
            reference_labels=regex_intent.reference_labels,
            user_goal=regex_intent.user_goal,
            confidence=llm_confidence,
        )

    return regex_intent


async def hybrid_parse_intent(
    prompt: str,
    image_count: int,
    llm_api_key: str = "",
    llm_base_url: str = "",
    llm_model_id: str = "",
    context_images: list[str] | None = None,
    context_messages: list[dict] | None = None,
    reference_labels: list[dict] | None = None,
) -> AgentIntent:
    intent = parse_agent_intent(
        prompt=prompt,
        image_count=image_count,
        context_messages=context_messages,
        reference_labels=reference_labels,
    )

    if intent.confidence >= HYBRID_CONFIDENCE_THRESHOLD:
        return intent

    if not llm_api_key:
        logger.debug(f"Regex confidence {intent.confidence:.2f} below threshold, but no LLM key available")
        return intent

    llm_result = await _classify_intent_with_llm(
        prompt=prompt,
        image_count=image_count,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model_id=llm_model_id,
        context_images=context_images,
    )

    return _pick_best_intent(intent, llm_result)


def validate_agent_result(intent: AgentIntent, result: dict) -> bool:
    if intent.task_type == "multi_independent":
        expected = intent.expected_count
        actual = len(result.get("final_images", []))
        return actual >= expected

    if intent.task_type == "single":
        actual = len(result.get("images", []))
        return actual >= intent.expected_count if intent.expected_count > 1 else actual >= 1

    return True


def _extract_context_image_urls(context_messages: list[dict] | None) -> list[str]:
    urls: list[str] = []
    for msg in (context_messages or []):
        for img_url in (msg.get("image_urls") or []):
            if img_url:
                urls.append(img_url)
    return urls


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


async def _generate_item_prompts(
    items: list[AgentItem],
    intent: AgentIntent,
    llm_provider_id: str,
    api_key: str,
    base_url: str = "",
    model_id: str = "",
    context_images: list[str] | None = None,
) -> list[str]:
    if not items:
        return []

    system_msg = (
        "You are a text-to-image prompt engineer. "
        "For each item below, write ONE concise English prompt optimized for image generation. "
        "Each prompt should be independent and self-contained. Do NOT generate a single sheet/turnaround "
        "unless the goal explicitly says 'sheet' or 'turnaround'. "
        "If reference images are provided, use their visual style and content to guide your prompts. "
        "Output a valid JSON array of strings, same length as input items. No markdown, no explanation."
    )
    user_msg = json.dumps({
        "goal": intent.user_goal,
        "items": [{"label": i.label, "hint": i.prompt_hint} for i in items],
        "output_format": "array of strings, one per item",
    }, ensure_ascii=False)

    try:
        client = LLMClient(
            base_url=base_url,
            api_key=api_key,
            model_id=model_id,
        )
        user_content = _build_multimodal_user_content(user_msg, context_images)
        result = await client.chat(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        prompts = json.loads(text)
        if isinstance(prompts, list) and len(prompts) == len(items):
            return [str(p) for p in prompts]
    except Exception as e:
        logger.warning(f"_generate_item_prompts LLM call failed: {e}, using fallback")

    return [f"{item.prompt_hint}, {intent.user_goal}" for item in items]


async def _generate_iterative_steps(
    prompt: str,
    llm_api_key: str,
    llm_base_url: str = "",
    llm_model_id: str = "",
    context_images: list[str] | None = None,
) -> list[dict]:
    system_msg = (
        "You are an image generation planner. The user wants to create images through iterative refinement. "
        "Break down the request into 2-5 sequential steps where each step builds on the previous one. "
        "Step 1 should be a rough draft/sketch, and later steps should progressively refine details. "
        "If reference images are provided, use their visual content to guide the refinement direction. "
        "Output a valid JSON array of objects. Each object has: "
        '"prompt" (string, English prompt for this step), '
        '"description" (string, brief Chinese description of this step), '
        '"image_count" (integer, default 1), '
        '"image_size" (string, default "1024x1024"). '
        "No markdown, no explanation, just the JSON array."
    )
    user_msg = json.dumps({"request": prompt}, ensure_ascii=False)

    try:
        client = LLMClient(base_url=llm_base_url, api_key=llm_api_key, model_id=llm_model_id)
        user_content = _build_multimodal_user_content(user_msg, context_images)
        result = await client.chat(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        steps = json.loads(text)
        if isinstance(steps, list) and len(steps) >= 1:
            valid_steps = []
            for s in steps:
                if isinstance(s, dict) and s.get("prompt"):
                    valid_steps.append({
                        "prompt": str(s["prompt"]),
                        "description": str(s.get("description", s["prompt"][:60])),
                        "image_count": int(s.get("image_count", 1)),
                        "image_size": str(s.get("image_size", "1024x1024")),
                    })
            if valid_steps:
                return valid_steps
    except Exception as e:
        logger.warning(f"_generate_iterative_steps LLM call failed: {e}, using fallback")

    return [{
        "prompt": prompt,
        "description": "直接生成",
        "image_count": 1,
        "image_size": "1024x1024",
    }]


async def _generate_radiate_params(
    prompt: str,
    expected_count: int,
    llm_api_key: str,
    llm_base_url: str = "",
    llm_model_id: str = "",
    context_images: list[str] | None = None,
) -> dict:
    system_msg = (
        "You are an image generation planner. The user wants to create a set of images with unified style/theme. "
        f"Generate exactly {expected_count} items, each with a distinct subject but sharing the same visual style. "
        "If reference images are provided, match their visual style (color palette, art style, composition) "
        "in all generated items. "
        "Output a valid JSON object with: "
        '"items" (array of objects, each with "prompt" string in English), '
        '"style" (string, visual style description in English), '
        '"overall_theme" (string, theme description in English). '
        "No markdown, no explanation, just the JSON object."
    )
    user_msg = json.dumps({"request": prompt, "count": expected_count}, ensure_ascii=False)

    try:
        client = LLMClient(base_url=llm_base_url, api_key=llm_api_key, model_id=llm_model_id)
        user_content = _build_multimodal_user_content(user_msg, context_images)
        result = await client.chat(
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
        )
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        params = json.loads(text)
        if isinstance(params, dict) and isinstance(params.get("items"), list) and len(params["items"]) >= 1:
            valid_items = []
            for it in params["items"]:
                if isinstance(it, dict) and it.get("prompt"):
                    valid_items.append({"prompt": str(it["prompt"])})
                elif isinstance(it, str):
                    valid_items.append({"prompt": it})
            if valid_items:
                return {
                    "items": valid_items,
                    "style": str(params.get("style", "")),
                    "overall_theme": str(params.get("overall_theme", "")),
                }
    except Exception as e:
        logger.warning(f"_generate_radiate_params LLM call failed: {e}, using fallback")

    items = _extract_items_from_text(prompt)
    if not items:
        for i in range(expected_count):
            items.append({"prompt": f"item {i + 1}, {prompt}"})
    return {
        "items": items,
        "style": _extract_style_from_text(prompt),
        "overall_theme": prompt[:50],
    }


def _extract_items_from_text(text: str) -> list[dict]:
    items = []
    emojis = {
        "开心": "happy expression", "难过": "sad expression", "生气": "angry expression",
        "愤怒": "angry furious expression",
        "惊讶": "surprised expression", "哭泣": "crying expression", "笑": "laughing smile expression",
        "爱": "love heart expression", "酷": "cool expression", "委屈": "upset expression",
        "晕": "dizzy expression", "害羞": "shy expression",
        "吃饭": "eating food expression", "睡觉": "sleeping expression",
        "胜利": "victory expression", "加油": "cheer expression", "疑问": "question expression",
        "无语": "speechless expression",
    }
    for kw, prompt in emojis.items():
        if kw in text:
            items.append({"prompt": prompt})
    return items


def _extract_style_from_text(text: str) -> str:
    style_map = {
        "可爱": "cute kawaii chibi", "炫酷": "cool cyberpunk neon",
        "MC": "Minecraft pixel blocky", "像素": "pixel art retro game",
        "猫": "cat character", "狗": "dog character",
        "emoji": "emoji sticker", "表情": "emoji expression sticker",
        "水墨": "ink wash painting", "水彩": "watercolor painting",
        "赛博朋克": "cyberpunk neon futuristic",
    }
    for kw, style in style_map.items():
        if kw in text:
            return style
    return "digital art illustration"


async def execute_multi_independent(
    db,
    session_id: str,
    intent: AgentIntent,
    data,
    task_manager,
    llm_provider_id: str,
    image_provider_id: str,
) -> dict:
    import asyncio

    from sqlalchemy import select
    from app.models.api_provider import ApiProvider
    from app.services.api_manager import resolve_provider_vendor
    from app.tools import registry
    from app.services.billing_service import calc_cost, record_billing

    steps: list[dict] = []
    final_images: list[dict] = []
    intermediate_images: list[dict] = []
    tokens_in_total = 0
    tokens_out_total = 0
    cost_total = 0.0

    if not intent.items:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="无法提取生成子项，请描述更具体")
        return {"error": "无法提取生成子项，请描述更具体", "images": [], "steps": []}

    llm_result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
    llm_prov = llm_result.scalar_one_or_none()
    if not llm_prov:
        task_manager.update_task(session_id, TaskStatus.ERROR, message="LLM provider not found")
        return {"error": "LLM provider not found", "images": [], "steps": []}

    try:
        base_url, api_key = await resolve_provider_vendor(db, llm_prov)
    except Exception as e:
        logger.error(f"Failed to decrypt LLM API key: {e}")
        task_manager.update_task(session_id, TaskStatus.ERROR, message="LLM API key decryption failed")
        return {"error": "LLM API key decryption failed", "images": [], "steps": []}
    image_size = getattr(data, "image_size", "1024x1024")

    context_images = _extract_context_image_urls(
        getattr(data, "context_messages", None)
    ) or None

    task_manager.update_task(session_id, TaskStatus.GENERATING,
        message=f"多图并行 | 生成 {len(intent.items)} 个子项的提示词")

    prompts = await _generate_item_prompts(
        items=intent.items,
        intent=intent,
        llm_provider_id=llm_provider_id,
        api_key=api_key,
        base_url=base_url,
        model_id=llm_prov.model_id,
        context_images=context_images,
    )

    steps.append({
        "type": "prompt_generation",
        "prompts": prompts,
    })

    async def _generate_one(item: AgentItem, prompt: str, idx: int) -> dict:
        refs = item.reference_urls or intent.references
        tool = registry.get("generate_image")
        if not tool:
            return {
                "item_id": item.id, "label": item.label, "url": "",
                "status": "failed", "error": "generate_image tool not found",
                "tokens_in": 0, "tokens_out": 0,
            }

        task_manager.update_task(session_id, TaskStatus.GENERATING,
            progress=idx + 1, total=len(intent.items),
            message=f"并行生成 {idx + 1}/{len(intent.items)}: {item.label[:20]}")

        result = await tool.execute(
            prompt=prompt,
            count=1,
            reference_urls=refs,
            reference_images=intent.reference_images or None,
            reference_labels=intent.reference_labels or None,
            db=db,
            image_provider_id=image_provider_id,
            image_size=image_size,
        )

        urls = result.meta.get("image_urls", []) if result.meta else []
        t_in = result.meta.get("tokens_in", 0) if result.meta else 0
        t_out = result.meta.get("tokens_out", 0) if result.meta else 0
        status = "ok" if urls else "failed"
        error = result.content if not urls else ""

        item_result = {
            "item_id": item.id,
            "label": item.label,
            "url": urls[0] if urls else "",
            "status": status,
            "error": error,
            "tokens_in": t_in,
            "tokens_out": t_out,
        }

        if image_provider_id:
            try:
                img_prov = await db.execute(
                    select(ApiProvider).where(ApiProvider.id == image_provider_id)
                )
                img_p = img_prov.scalar_one_or_none()
                if img_p:
                    img_cost = calc_cost(img_p, tokens_in=t_in, tokens_out=t_out, call_count=1)
                    await record_billing(
                        db,
                        session_id=session_id,
                        provider_id=img_p.id,
                        billing_type=img_p.billing_type.value if hasattr(img_p.billing_type, "value") else str(img_p.billing_type),
                        tokens_in=t_in,
                        tokens_out=t_out,
                        cost=img_cost,
                        currency=img_p.currency,
                        detail={
                            "type": "image_gen",
                            "agent": True,
                            "intent": "multi_independent",
                            "item": item.label,
                        },
                    )
                    item_result["cost"] = img_cost
            except Exception as e:
                logger.debug(f"Billing record failed for item {item.id}: {e}")

        steps.append({
            "type": "tool_result",
            "name": "generate_image",
            "item_id": item.id,
            "label": item.label,
            "content": result.content[:500] if result.content else "",
            "args": {"prompt": prompt, "count": 1},
            "meta": {"image_urls": urls},
        })

        return item_result

    results = await asyncio.gather(
        *[_generate_one(item, prompt, i) for i, (item, prompt) in enumerate(zip(intent.items, prompts))],
        return_exceptions=True,
    )

    final_output_parts: list[str] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            final_images.append({
                "item_id": intent.items[i].id,
                "label": intent.items[i].label,
                "url": "",
                "status": "failed",
                "error": str(r),
            })
            final_output_parts.append(f"- {intent.items[i].label}: 生成异常 ({r})")
        else:
            final_images.append(r)
            if r["status"] == "ok":
                tokens_in_total += r.get("tokens_in", 0)
                tokens_out_total += r.get("tokens_out", 0)
                cost_total += r.get("cost", 0)
                final_output_parts.append(f"- {r['label']}: 已生成")
            else:
                final_output_parts.append(f"- {r['label']}: 失败 ({r.get('error', 'unknown')})")

    final_output = "已生成:\n" + "\n".join(final_output_parts)

    all_urls = [img["url"] for img in final_images if img.get("url")]

    return {
        "output": final_output,
        "steps": steps,
        "cost": cost_total,
        "tokens_in": tokens_in_total,
        "tokens_out": tokens_out_total,
        "cancelled": False,
        "images": all_urls,
        "intent": {
            "task_type": intent.task_type,
            "expected_count": intent.expected_count,
            "items": [{"id": i.id, "label": i.label} for i in intent.items],
        },
        "final_images": final_images,
        "intermediate_images": intermediate_images,
    }
