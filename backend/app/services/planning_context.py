import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageRole, MessageType

logger = logging.getLogger(__name__)

TOKEN_BUDGET_HARD_CAP = 6000
TOKEN_BUDGET_LAYERS = {
    "system": 500,
    "skill_bias": 200,
    "input": 500,
    "images": 2000,
    "history": 1500,
    "search": 800,
}

RELEVANCE_THRESHOLD = 0.3


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = len(text) - cjk
    return cjk + other // 4


def _estimate_image_tokens(image_count: int) -> int:
    return image_count * 85


class PlanningContextManager:
    def __init__(
        self,
        session_id: str = "",
        prompt: str = "",
        negative_prompt: str = "",
        image_count: int = 1,
        image_size: str = "1024x1024",
        reference_images: list[str] | None = None,
        context_images: list[str] | None = None,
        context_reference_urls: list[str] | None = None,
        reference_labels: list[dict] | None = None,
        search_context: str = "",
        skill_hints: dict | None = None,
    ):
        self.session_id = session_id
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.image_count = image_count
        self.image_size = image_size
        self.reference_images = reference_images or []
        self.context_images = context_images or []
        self.context_reference_urls = context_reference_urls or []
        self.reference_labels = reference_labels or []
        self.search_context = search_context
        self.skill_hints = skill_hints
        self._image_descriptions: dict[str, str] = {}

    def budget_tokens(self) -> dict:
        prompt_tokens = _estimate_tokens(self.prompt)
        search_tokens = _estimate_tokens(self.search_context)
        image_tokens = _estimate_image_tokens(
            len(self.context_images) + len(self.reference_images)
        )
        skill_tokens = 0
        if self.skill_hints:
            skill_tokens = _estimate_tokens(str(self.skill_hints))

        allocated = {
            "system": TOKEN_BUDGET_LAYERS["system"],
            "skill_bias": min(skill_tokens, TOKEN_BUDGET_LAYERS["skill_bias"]) if self.skill_hints else 0,
            "input": min(prompt_tokens, TOKEN_BUDGET_LAYERS["input"]),
            "images": min(image_tokens, TOKEN_BUDGET_LAYERS["images"]),
            "history": TOKEN_BUDGET_LAYERS["history"],
            "search": min(search_tokens, TOKEN_BUDGET_LAYERS["search"]) if self.search_context else 0,
        }

        total = sum(allocated.values())
        if total > TOKEN_BUDGET_HARD_CAP:
            overflow = total - TOKEN_BUDGET_HARD_CAP
            truncation_order = ["search", "history", "input"]
            for key in truncation_order:
                if overflow <= 0:
                    break
                reduction = min(allocated[key], overflow)
                allocated[key] -= reduction
                overflow -= reduction

        allocated["total"] = sum(allocated.values())
        allocated["hard_cap"] = TOKEN_BUDGET_HARD_CAP
        return allocated

    def deduplicate_images(self) -> dict:
        seen: set[str] = set()
        deduped_refs: list[str] = []
        deduped_context: list[str] = []
        deduped_urls: list[str] = []

        for img in self.reference_images:
            key = img[:200] if img.startswith("data:") else img
            if key not in seen:
                seen.add(key)
                deduped_refs.append(img)

        for url in self.context_images:
            if url not in seen:
                seen.add(url)
                deduped_context.append(url)

        for url in self.context_reference_urls:
            if url not in seen:
                seen.add(url)
                deduped_urls.append(url)

        self.reference_images = deduped_refs
        self.context_images = deduped_context
        self.context_reference_urls = deduped_urls

        return {
            "reference_images": deduped_refs,
            "context_images": deduped_context,
            "context_reference_urls": deduped_urls,
        }

    def compute_relevance(self, context_item: str) -> float:
        if not self.prompt or not context_item:
            return 0.5
        prompt_words = set(re.findall(r"\w+", self.prompt.lower()))
        item_words = set(re.findall(r"\w+", context_item.lower()))
        if not prompt_words or not item_words:
            return 0.5
        overlap = len(prompt_words & item_words)
        union = len(prompt_words | item_words)
        return overlap / union if union > 0 else 0.0

    def apply_relevance_filter(self, history_messages: list[dict]) -> list[dict]:
        if not history_messages:
            return []

        filtered: list[dict] = []
        for msg in history_messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
                content = " ".join(text_parts)

            relevance = self.compute_relevance(content)
            msg["_relevance"] = relevance

            if relevance < RELEVANCE_THRESHOLD:
                msg["_budget_weight"] = 0.5
            else:
                msg["_budget_weight"] = 1.0

            filtered.append(msg)

        return filtered

    async def cache_image_descriptions(
        self,
        db: AsyncSession,
        image_urls: list[str],
        llm_api_key: str = "",
        llm_base_url: str = "",
        llm_model_id: str = "",
        task_manager=None,
        session_id: str = "",
    ) -> dict[str, str]:
        if not image_urls:
            return {}

        cached: dict[str, str] = {}
        uncached: list[str] = []

        if db and self.session_id:
            try:
                result = await db.execute(
                    select(Message)
                    .where(
                        Message.session_id == self.session_id,
                        Message.role == MessageRole.assistant,
                    )
                    .order_by(Message.created_at.desc())
                    .limit(50)
                )
                messages = result.scalars().all()
                for msg in messages:
                    meta = msg.metadata_ if isinstance(msg.metadata_, dict) else {}
                    desc_cache = meta.get("image_descriptions", {})
                    if isinstance(desc_cache, dict):
                        self._image_descriptions.update(desc_cache)
            except Exception:
                pass

        for url in image_urls:
            if url in self._image_descriptions:
                cached[url] = self._image_descriptions[url]
            else:
                uncached.append(url)

        if uncached and llm_api_key:
            from app.utils.llm_client import LLMClient
            from app.core.events import LamEvent

            client = LLMClient(base_url=llm_base_url, api_key=llm_api_key, model_id=llm_model_id)
            for url in uncached[:4]:
                try:
                    full_text = ""
                    usage_data = None
                    async for delta, usage in client.chat_stream(
                        messages=[
                            {
                                "role": "system",
                                "content": "Describe this image in 2-3 concise English sentences. Focus on style, colors, composition, and subject.",
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Describe this image briefly."},
                                    {"type": "image_url", "image_url": {"url": url, "detail": "low"}},
                                ],
                            },
                        ],
                        temperature=0.3,
                    ):
                        full_text += delta
                        if task_manager:
                            await task_manager.publish(LamEvent(
                                event_type="task_progress",
                                correlation_id=f"agent-{session_id}",
                                payload={
                                    "type": "agent_token",
                                    "session_id": session_id,
                                    "node": "context",
                                    "content": delta,
                                },
                            ))
                        if usage:
                            usage_data = usage
                    if full_text:
                        cached[url] = full_text
                        self._image_descriptions[url] = full_text
                except Exception as e:
                    logger.warning(f"Failed to describe image {url[:50]}: {e}")

        return cached

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "image_count": self.image_count,
            "image_size": self.image_size,
            "reference_images": self.reference_images,
            "context_images": self.context_images,
            "context_reference_urls": self.context_reference_urls,
            "reference_labels": self.reference_labels,
            "search_context": self.search_context,
            "skill_hints": self.skill_hints,
            "token_budget": self.budget_tokens(),
            "image_descriptions": self._image_descriptions,
        }
