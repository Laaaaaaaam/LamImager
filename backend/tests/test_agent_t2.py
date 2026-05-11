from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.session import GenerateRequest
from app.services.generate_service import handle_agent_generate
from app.utils.image_client import ImageClient

from .conftest import build_mock_llm_rounds

IMAGE_URLS = [
    "https://fake.test/cat_watercolor.png",
    "https://fake.test/cat_oil.png",
    "https://fake.test/cat_pixel.png",
    "https://fake.test/cat_lineart.png",
]
_url_iter = iter(IMAGE_URLS)


def _next_url():
    try:
        return [next(_url_iter)]
    except StopIteration:
        return ["https://fake.test/cat_fallback.png"]


@pytest.mark.asyncio
async def test_multi_image_parallel_strategy(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """
    T2: 生成4张不同风格的猫咪插画：水彩、油画、像素风、线稿
    Agent 调用 plan(action="create", strategy="parallel")，再 plan(action="apply")，再多次 generate_image。
    """
    global _url_iter
    _url_iter = iter(IMAGE_URLS)

    mocker.patch(
        "app.utils.image_client.ImageClient.generate",
        return_value={"data": [{"url": "https://fake.test/gen.png"}]},
    )
    mocker.patch(
        "app.utils.image_client.ImageClient.extract_images",
        side_effect=_next_url,
    )
    mocker.patch(
        "app.utils.image_client.ImageClient.extract_images_from_chat",
        side_effect=_next_url,
    )

    rounds = build_mock_llm_rounds([
        # Round 1: plan(action="create") → create parallel template
        [
            {
                "id": "call_t2_1",
                "type": "function",
                "function": {
                    "name": "plan",
                    "arguments": json.dumps({
                        "action": "create",
                        "name": "猫咪风格插画",
                        "strategy": "parallel",
                        "steps": [
                            {"prompt": "A cute cat illustration, watercolor painting style, soft brushstrokes", "description": "水彩猫咪", "image_count": 1},
                            {"prompt": "A cute cat illustration, oil painting style, rich texture", "description": "油画猫咪", "image_count": 1},
                            {"prompt": "A cute cat illustration, pixel art style, retro 8-bit game", "description": "像素猫咪", "image_count": 1},
                            {"prompt": "A cute cat illustration, line art style, ink sketch", "description": "线稿猫咪", "image_count": 1},
                        ],
                    }),
                },
            },
        ],
        # Round 2: plan(action="apply") → apply the created template
        [
            {
                "id": "call_t2_2",
                "type": "function",
                "function": {
                    "name": "plan",
                    "arguments": json.dumps({
                        "action": "apply",
                        "template_id": "WILL_BE_QUERIED_FROM_DB",  # 由 plan tool 内部查询
                        "variables": {},
                    }),
                },
            },
        ],
        # Round 3: generate_image × 4
        [
            {
                "id": "call_t2_3a",
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "arguments": json.dumps({
                        "prompt": "A cute cat illustration, watercolor painting style, soft brushstrokes",
                        "count": 1,
                    }),
                },
            },
            {
                "id": "call_t2_3b",
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "arguments": json.dumps({
                        "prompt": "A cute cat illustration, oil painting style, rich texture",
                        "count": 1,
                    }),
                },
            },
            {
                "id": "call_t2_3c",
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "arguments": json.dumps({
                        "prompt": "A cute cat illustration, pixel art style, retro 8-bit game",
                        "count": 1,
                    }),
                },
            },
            {
                "id": "call_t2_3d",
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "arguments": json.dumps({
                        "prompt": "A cute cat illustration, line art style, ink sketch",
                        "count": 1,
                    }),
                },
            },
        ],
        [],  # round 4: no tool_calls → loop breaks
    ])
    mocker.patch("app.services.agent_service.LLMClient.chat_stream_with_tools", new=rounds)

    result = await handle_agent_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="生成4张不同风格的猫咪插画：水彩、油画、像素风、线稿",
            agent_mode=True,
            agent_tools=[],
        ),
    )

    assert result.get("cancelled") == False
    assert "images" in result

    plan_tool_calls = [
        s for s in result.get("steps", [])
        if s.get("name") == "plan" and s.get("type") == "tool_call"
    ]
    assert len(plan_tool_calls) >= 1, "T2 should call plan at least once"

    gen_tool_calls = [
        s for s in result.get("steps", [])
        if s.get("name") == "generate_image" and s.get("type") == "tool_call"
    ]
    assert len(gen_tool_calls) >= 4, "T2 should call generate_image at least 4 times"

    plan_indices = [
        i for i, s in enumerate(result.get("steps", []))
        if s.get("name") == "plan" and s.get("type") == "tool_call"
    ]
    gen_indices = [
        i for i, s in enumerate(result.get("steps", []))
        if s.get("name") == "generate_image" and s.get("type") == "tool_call"
    ]
    if plan_indices and gen_indices:
        assert plan_indices[-1] < gen_indices[0], (
            "T2: plan must be called BEFORE generate_image"
        )
