import logging
import re
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class SessionImage:
    url: str
    message_id: str = ""
    message_index: int = 0
    is_from_latest: bool = False


@dataclass
class ImageContextResolution:
    mode: Literal["new_generation", "edit_target", "batch_edit", "style_reference", "ask_clarification"]
    target_images: list[str] = field(default_factory=list)
    reference_images: list[str] = field(default_factory=list)
    context_images: list[str] = field(default_factory=list)
    reason: str = ""
    confidence: float = 0.0
    clarification: str = ""


MODIFY_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"改", r"修", r"调", r"换", r"变", r"去掉", r"加上", r"减掉", r"删",
        r"线稿化", r"素描化", r"卡通化", r"油画化", r"水彩化", r"扁平化",
        r"优化", r"精修", r"就这个方向",
        r"增加", r"加细", r"减少",
        r"更", r"稍微", r"一点",
        r"背景.*改", r"背景.*去", r"脸.*改", r"颜色.*换", r"配色.*换",
        r"构图.*调", r"姿势.*换",
        r"modify", r"change", r"adjust", r"fix", r"remove", r"add",
        r"refine\b", r"improve", r"optimize",
    ]
]

GROUP_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"这组", r"这几张", r"整套", r"整套都", r"这套", r"全部都", r"都.*改",
        r"都.*换", r"都.*修",
    ]
]

STYLE_REF_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"照这个风格", r"参考.*氛围", r"用.*配色", r"构图像", r"风格像",
        r"参考.*风格", r"照.*风格",
    ]
]

NEW_GEN_INTENT_PATTERNS = [
    re.compile(p)
    for p in [
        r"再画", r"再生成", r"再来", r"来个新", r"换个完全不同", r"生成一张",
        r"新方案", r"重新画", r"重新生成", r"全新",
        r"继续画", r"继续生成", r"继续做",
        r"画一", r"画只", r"画个", r"画张",
        r"生成一", r"生成只", r"生成个",
    ]
]

EXPLICIT_IMAGE_REF_PATTERNS = [
    (re.compile(r"第([一二三四五六七八九十\d]+)张"), 1),
    (re.compile(r"第(\d+)张"), 1),
    (re.compile(r"图([一二三四五六七八九十\d]+)"), 1),
    (re.compile(r"图(\d+)"), 1),
]

CN_NUM_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_cn_num(s: str) -> int | None:
    if s.isdigit():
        return int(s)
    return CN_NUM_MAP.get(s)


def detect_image_intent(prompt: str) -> Literal["edit_target", "batch_edit", "style_reference", "new_generation", "ambiguous"]:
    lower = prompt.lower().strip()

    for pat in STYLE_REF_INTENT_PATTERNS:
        if pat.search(lower):
            return "style_reference"

    for pat in GROUP_INTENT_PATTERNS:
        if pat.search(lower):
            return "batch_edit"

    for pat in NEW_GEN_INTENT_PATTERNS:
        if pat.search(lower):
            return "new_generation"

    for pat in MODIFY_INTENT_PATTERNS:
        if pat.search(lower):
            return "edit_target"

    return "new_generation"


def resolve_explicit_image_refs(
    prompt: str,
    session_images: list[SessionImage],
) -> list[SessionImage]:
    if not session_images:
        return []

    matched_indices: set[int] = set()

    for pat, _ in EXPLICIT_IMAGE_REF_PATTERNS:
        for m in pat.finditer(prompt):
            raw = m.group(1)
            num = _parse_cn_num(raw)
            if num is not None and 1 <= num <= len(session_images):
                matched_indices.add(num - 1)

    if not matched_indices:
        return []

    return [session_images[i] for i in sorted(matched_indices)]


class ImageContextResolver:
    def resolve_image_context(
        self,
        prompt: str,
        session_images: list[SessionImage],
        manual_refine_images: list[str] | None = None,
        selected_image_url: str = "",
        refine_mode: bool = False,
    ) -> ImageContextResolution:
        if manual_refine_images is None:
            manual_refine_images = []

        # Priority 1: manual refine mode with explicit images
        if refine_mode and manual_refine_images:
            return ImageContextResolution(
                mode="edit_target",
                target_images=manual_refine_images[:1],
                reason="refine_mode with explicit images",
                confidence=1.0,
            )

        # Priority 1b: refine_mode without explicit images — force edit_target
        if refine_mode:
            target = selected_image_url or self._get_latest_editable_image(session_images) or ""
            if target:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[target],
                    reason="refine_mode forced edit_target",
                    confidence=1.0,
                )
            return ImageContextResolution(
                mode="new_generation",
                reason="refine_mode but no images available",
                confidence=0.5,
            )

        # Priority 1c: selected image URL (non-refine)
        if selected_image_url:
            intent = detect_image_intent(prompt)
            if intent in ("edit_target", "batch_edit", "style_reference"):
                return ImageContextResolution(
                    mode=intent,
                    target_images=[selected_image_url],
                    reason=f"selected_image_url + intent={intent}",
                    confidence=0.95,
                )

        # Priority 2: explicit image refs in prompt
        explicit_refs = resolve_explicit_image_refs(prompt, session_images)
        if explicit_refs:
            intent = detect_image_intent(prompt)
            mode = intent if intent != "new_generation" else "edit_target"
            urls = [img.url for img in explicit_refs]
            if mode == "batch_edit":
                urls = urls[:4]
            else:
                urls = urls[:1]
            return ImageContextResolution(
                mode=mode,
                target_images=urls,
                reason=f"explicit image refs: {[img.message_index for img in explicit_refs]}, intent={intent}",
                confidence=0.9,
            )

        # Priority 3-5: intent-based selection
        intent = detect_image_intent(prompt)

        if intent == "new_generation":
            return ImageContextResolution(
                mode="new_generation",
                reason="no modify intent detected",
                confidence=0.8,
            )

        if intent == "style_reference":
            latest = self._get_latest_editable_image(session_images)
            if latest:
                return ImageContextResolution(
                    mode="style_reference",
                    reference_images=[latest],
                    reason="style_reference intent, using latest image as style ref",
                    confidence=0.7,
                )
            return ImageContextResolution(
                mode="new_generation",
                reason="style_reference intent but no images in session",
                confidence=0.5,
            )

        if intent == "batch_edit":
            latest_group = self._get_latest_image_group(session_images)
            if len(latest_group) > 1:
                return ImageContextResolution(
                    mode="batch_edit",
                    target_images=latest_group[:4],
                    reason=f"batch_edit intent, {len(latest_group)} images in latest group",
                    confidence=0.7,
                )
            latest = self._get_latest_editable_image(session_images)
            if latest:
                return ImageContextResolution(
                    mode="edit_target",
                    target_images=[latest],
                    reason="batch_edit intent but only 1 image, falling back to edit_target",
                    confidence=0.6,
                )
            return ImageContextResolution(
                mode="new_generation",
                reason="batch_edit intent but no images in session",
                confidence=0.5,
            )

        # intent == "edit_target" or "ambiguous"
        latest = self._get_latest_editable_image(session_images)
        if not latest:
            return ImageContextResolution(
                mode="new_generation",
                reason="edit intent but no images in session",
                confidence=0.5,
            )

        # Ambiguity Gate: multiple images in latest message, user didn't specify which
        latest_group = self._get_latest_image_group(session_images)
        if len(latest_group) > 1:
            return ImageContextResolution(
                mode="ask_clarification",
                clarification=f"你要修改哪一张？图1、图2、图3还是图4？" if len(latest_group) <= 4 else f"你要修改哪一张？最近{len(latest_group)}张图。",
                reason=f"edit intent but {len(latest_group)} images in latest message, ambiguous target",
                confidence=0.6,
            )

        # Single image: auto-select
        return ImageContextResolution(
            mode="edit_target",
            target_images=[latest],
            reason="edit intent, single image in latest message, auto-selected",
            confidence=0.85,
        )

    def _get_latest_editable_image(self, session_images: list[SessionImage]) -> str | None:
        for img in session_images:
            if img.is_from_latest and img.url.startswith("http"):
                return img.url
        for img in session_images:
            if img.url.startswith("http"):
                return img.url
        return None

    def _get_latest_image_group(self, session_images: list[SessionImage]) -> list[str]:
        if not session_images:
            return []
        latest_idx = session_images[0].message_index
        group: list[str] = []
        for img in session_images:
            if img.message_index == latest_idx and img.url.startswith("http"):
                group.append(img.url)
            else:
                break
        return group
