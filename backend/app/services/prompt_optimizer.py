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
            tokens_in = sum(LLMClient.estimate_tokens(m["content"]) for m in messages)

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
    "detail_enhancement": """You are a prompt optimization assistant. Enhance the given image generation prompt by adding more specific visual details, textures, lighting conditions, and atmospheric elements. Keep the original intent but make it more vivid and descriptive.

Original prompt: {prompt}

Provide ONLY the enhanced prompt, no explanations.""",

    "style_unification": """You are a prompt optimization assistant. Refine the given image generation prompt for consistent artistic style, color harmony, and visual coherence. Ensure the style description is clear and unified.

Original prompt: {prompt}

Provide ONLY the refined prompt, no explanations.""",

    "composition_optimization": """You are a prompt optimization assistant. Optimize the given image generation prompt for better composition, framing, focal point, and visual balance. Add composition-specific keywords and spatial descriptions.

Original prompt: {prompt}

Provide ONLY the optimized prompt, no explanations.""",

    "color_adjustment": """You are an expert color theorist and image generation prompt engineer. Refine the given image generation prompt to achieve superior color harmony, mood-appropriate palettes, and atmospheric color grading. Consider complementary colors, color temperature, saturation balance, and how color supports the emotional intent of the image.

Original prompt: {prompt}

Provide ONLY the refined prompt, no explanations.""",

    "lighting_enhancement": """You are an expert lighting designer and image generation prompt engineer. Enhance the given image generation prompt with sophisticated lighting descriptions. Consider light sources (natural, artificial, ambient), light direction and angle, shadow casting, volumetric lighting, rim lighting, and light color temperature. Add specific lighting techniques that enhance depth, drama, and atmosphere.

Original prompt: {prompt}

Provide ONLY the refined prompt, no explanations.""",
}

# Focus descriptions for multi-direction merging (no repeated prompt/footer)
OPTIMIZATION_FOCUSES = {
    "detail_enhancement": "Add more specific visual details, textures, lighting conditions, and atmospheric elements. Keep the original intent but make it more vivid and descriptive.",
    "style_unification": "Ensure consistent artistic style, color harmony, and visual coherence. Make the style description clear and unified.",
    "composition_optimization": "Improve composition, framing, focal point, and visual balance. Add composition-specific keywords and spatial descriptions.",
    "color_adjustment": "Achieve superior color harmony, mood-appropriate palettes, and atmospheric color grading. Consider complementary colors, color temperature, and saturation balance.",
    "lighting_enhancement": "Add sophisticated lighting descriptions: light sources, direction, shadow casting, volumetric lighting, rim lighting, and light color temperature.",
}

CUSTOM_OPTIMIZATION_PROMPT = """You are a prompt optimization assistant. Optimize the given image generation prompt following the user's custom instruction carefully.

Custom instruction: {instruction}

Original prompt: {prompt}

Provide ONLY the optimized prompt, no explanations."""

DEFAULT_OPTIMIZATION_PROMPT = """You are a prompt optimization assistant. Optimize the given image generation prompt to make it more descriptive, vivid, and effective for image generation.

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
        "Optimize the following prompt by simultaneously applying ALL of these focuses:\n"
        + "\n".join(focuses)
        + f"\n\nOriginal prompt: {prompt}"
        + "\n\nProvide ONLY the refined prompt, no explanations."
    )


async def optimize_prompt(
    db: AsyncSession, data: PromptOptimizeRequest
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
        tokens_in = sum(LLMClient.estimate_tokens(m["content"]) for m in messages)

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
