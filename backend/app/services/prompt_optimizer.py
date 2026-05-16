from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_provider import ApiProvider
from app.services.billing_service import record_billing, calc_cost
from app.schemas.prompt import PromptOptimizeRequest, PromptOptimizeResponse
from app.services.api_manager import resolve_provider_vendor
from app.utils.llm_client import LLMClient


async def stream_llm_chat(
    db: AsyncSession,
    provider_id: str,
    messages: list[dict],
    temperature: float = 0.7,
    session_id: str | None = None,
    stream_type: str = "assistant",
):
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        yield f"data: {json.dumps({'error': 'LLM provider not found'})}\n\n"
        return

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        yield f"data: {json.dumps({'error': f'API key decryption failed: {e}'})}\n\n"
        return

    client = LLMClient(base_url, api_key, provider.model_id)

    full_response = []
    usage_from_api = None
    try:
        async for content, usage_data in client.chat_stream(messages, temperature=temperature):
            if content:
                full_response.append(content)
                yield f"data: {json.dumps({'token': content})}\n\n"
            if usage_data:
                usage_from_api = usage_data

        full_text = "".join(full_response)

        if usage_from_api:
            tokens_in = usage_from_api["prompt_tokens"]
            tokens_out = usage_from_api["completion_tokens"]
        else:
            tokens_out = LLMClient.estimate_tokens(full_text)
            tokens_in = sum(
                LLMClient.estimate_tokens(m["content"] if isinstance(m["content"], str) else str(m["content"]))
                for m in messages
            )

        cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=1)

        await record_billing(
            db,
            session_id=session_id,
            provider_id=provider.id,
            billing_type=provider.billing_type.value,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            currency=provider.currency,
            detail={"type": stream_type},
        )

        yield f"data: {json.dumps({'done': True, 'cost': cost})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

OPTIMIZATION_PROMPTS = {
    "detail_enhancement": """You are a prompt optimization assistant. Enhance the given image generation prompt by making vague descriptions more specific and vivid. Only add details where the original is genuinely vague — if a detail is already clear, keep it as-is. Do not pile on adjectives or generic quality keywords.

Original prompt: {prompt}

Provide ONLY the enhanced prompt, no explanations.""",

    "style_unification": """You are a prompt optimization assistant. Refine the given image generation prompt for consistent artistic style and visual coherence. Only add style descriptors when they serve the image's intent — do not force a style onto a prompt that doesn't need one.

Original prompt: {prompt}

Provide ONLY the refined prompt, no explanations.""",

    "composition_optimization": """You are a prompt optimization assistant. Optimize the given image generation prompt for better composition and visual balance. Only add composition guidance when it meaningfully improves the image — skip for simple subjects where composition is not the focus.

Original prompt: {prompt}

Provide ONLY the optimized prompt, no explanations.""",

    "color_adjustment": """You are a prompt optimization assistant. Refine the given image generation prompt for better color harmony and mood-appropriate palettes. Only add color direction when color is relevant to the intent — do not force color theory onto prompts where it adds no value.

Original prompt: {prompt}

Provide ONLY the refined prompt, no explanations.""",

    "lighting_enhancement": """You are a prompt optimization assistant. Enhance the given image generation prompt with lighting descriptions when lighting matters to the mood or atmosphere. Only add lighting details when they serve the image's intent — do not add lighting to every prompt by default.

Original prompt: {prompt}

Provide ONLY the refined prompt, no explanations.""",
}

# Focus descriptions for multi-direction merging (no repeated prompt/footer)
OPTIMIZATION_FOCUSES = {
    "detail_enhancement": "Make vague descriptions more specific and vivid. Only add details where genuinely vague — do not pile on adjectives or generic quality keywords.",
    "style_unification": "Ensure consistent artistic style and visual coherence. Only add style descriptors when they serve the image's intent.",
    "composition_optimization": "Improve composition and visual balance. Only add composition guidance when it meaningfully improves the image.",
    "color_adjustment": "Achieve better color harmony and mood-appropriate palettes. Only add color direction when color is relevant to the intent.",
    "lighting_enhancement": "Add lighting descriptions when lighting matters to the mood or atmosphere. Do not add lighting to every prompt by default.",
}

CUSTOM_OPTIMIZATION_PROMPT = """You are a prompt optimization assistant. Optimize the given image generation prompt following the user's custom instruction carefully. Do not over-embellish — apply the instruction precisely without adding unnecessary details.

Custom instruction: {instruction}

Original prompt: {prompt}

Provide ONLY the optimized prompt, no explanations."""

DEFAULT_OPTIMIZATION_PROMPT = """You are a prompt optimization assistant. Optimize the given image generation prompt to make it more effective for image generation. Only expand vague parts — if the prompt is already specific, keep it concise. Do not add generic quality keywords or unnecessary details.

Original prompt: {prompt}

Provide ONLY the optimized prompt, no explanations."""


def build_optimization_prompt(direction_str: str, prompt: str) -> str:
    knowledge_directions = [d.strip() for d in direction_str.split(",") if d.strip()]
    known = [d for d in knowledge_directions if d in OPTIMIZATION_PROMPTS]
    has_custom = any(d.startswith("custom:") for d in knowledge_directions)
    custom_instruction = ""
    if has_custom:
        for d in knowledge_directions:
            if d.startswith("custom:"):
                custom_instruction = d[7:].strip()
                break

    if len(known) == 1 and not has_custom:
        return OPTIMIZATION_PROMPTS[known[0]].format(prompt=prompt)

    if not known and not has_custom:
        return DEFAULT_OPTIMIZATION_PROMPT.format(prompt=prompt)

    if not known and has_custom:
        return CUSTOM_OPTIMIZATION_PROMPT.format(instruction=custom_instruction, prompt=prompt)

    focuses = []
    for d in known:
        focuses.append(f"- {OPTIMIZATION_FOCUSES[d]}")
    if has_custom and custom_instruction:
        focuses.append(f"- Custom instruction: {custom_instruction}")

    return (
        "You are an expert image generation prompt engineer. "
        "Optimize the following prompt by applying these focuses where they genuinely improve the result. "
        "Do NOT apply every focus mechanically — skip any focus that would add noise rather than value for this specific prompt. "
        "Less is more when the original prompt is already clear.\n\n"
        + "\n".join(focuses)
        + f"\n\nOriginal prompt: {prompt}"
        + "\n\nProvide ONLY the refined prompt, no explanations."
    )


async def optimize_prompt(
    db: AsyncSession, data: PromptOptimizeRequest,
    context_images: list[str] | None = None,
) -> PromptOptimizeResponse:
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == data.llm_provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        raise ValueError("LLM provider not found")

    direction = data.direction

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        raise ValueError(f"LLM API key decryption failed: {e}") from e

    client = LLMClient(base_url, api_key, provider.model_id)

    system_prompt = build_optimization_prompt(direction, data.prompt)

    if data.multimodal_context:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": data.multimodal_context + [
                {"type": "text", "text": f"\n\n根据上述上下文和参考图片，优化以下生图提示词:\n{data.prompt}"}
            ]},
        ]
    elif context_images:
        user_content: list[dict] = [
            {"type": "text", "text": f"根据参考图片，优化以下生图提示词:\n{data.prompt}"},
        ]
        for img_url in context_images[:2]:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": img_url, "detail": "auto"},
            })
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": data.prompt},
        ]

    response = await client.chat(messages, temperature=0.7)
    optimized = LLMClient.extract_content(response)

    tokens_in = response.get("usage", {}).get("prompt_tokens", 0)
    tokens_out = response.get("usage", {}).get("completion_tokens", 0)

    cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=1)

    await record_billing(
        db,
        session_id=data.session_id,
        provider_id=provider.id,
        billing_type=provider.billing_type.value,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost=cost,
        currency=provider.currency,
        detail={"prompt": data.prompt[:100], "direction": direction, "type": "optimize"},
    )

    return PromptOptimizeResponse(
        original=data.prompt,
        optimized=optimized,
        direction=direction,
    )


async def optimize_prompt_stream(
    db: AsyncSession, data: PromptOptimizeRequest,
):
    result = await db.execute(select(ApiProvider).where(ApiProvider.id == data.llm_provider_id))
    provider = result.scalar_one_or_none()
    if not provider:
        yield f"data: {json.dumps({'error': 'LLM provider not found'})}\n\n"
        return

    try:
        base_url, api_key = await resolve_provider_vendor(db, provider)
    except Exception as e:
        yield f"data: {json.dumps({'error': f'API key decryption failed: {e}'})}\n\n"
        return

    client = LLMClient(base_url, api_key, provider.model_id)

    system_prompt = build_optimization_prompt(data.direction, data.prompt)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": data.prompt},
    ]

    full_response = []
    try:
        async for content, usage_data in client.chat_stream(messages, temperature=0.7):
            if content:
                full_response.append(content)
                yield f"data: {json.dumps({'token': content})}\n\n"

        full_text = "".join(full_response)

        tokens_out = LLMClient.estimate_tokens(full_text)
        tokens_in = sum(
            LLMClient.estimate_tokens(m["content"] if isinstance(m["content"], str) else str(m["content"]))
            for m in messages
        )

        cost = calc_cost(provider, tokens_in=tokens_in, tokens_out=tokens_out, call_count=1)

        await record_billing(
            db,
            session_id=data.session_id,
            provider_id=provider.id,
            billing_type=provider.billing_type.value,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=cost,
            currency=provider.currency,
            detail={"prompt": data.prompt[:100], "direction": data.direction, "type": "optimize"},
        )

        yield f"data: {json.dumps({'done': True, 'cost': cost})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
