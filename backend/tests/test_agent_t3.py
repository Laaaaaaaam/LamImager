from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan_template import PlanTemplate
from app.schemas.session import GenerateRequest
from app.services.generate_service import handle_agent_generate

from .conftest import build_mock_llm_rounds

FAKE_CELL_B64 = [
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk",
    "+M9QDwADgQGA1A4BTAAAAABJRU5ErkJggg==",
] * 6
FAKE_ITEM_URLS = [
    "https://fake.test/orange_cat_happy.png",
    "https://fake.test/orange_cat_sad.png",
    "https://fake.test/orange_cat_angry.png",
    "https://fake.test/orange_cat_surprised.png",
    "https://fake.test/orange_cat_sleeping.png",
    "https://fake.test/orange_cat_eating.png",
]
_item_url_iter = iter(FAKE_ITEM_URLS)


def _next_item_url(*args, **kwargs):
    try:
        return [next(_item_url_iter)]
    except StopIteration:
        return ["https://fake.test/orange_cat_fallback.png"]


@pytest.mark.asyncio
async def test_radiate_strategy(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """
    T3: 帮我生成一套6个表情包，主角是一只橘猫，包含开心、难过、愤怒、惊讶、睡觉、吃饭
    触发 radiate 策略，生成锚点网格图，再逐项扩展。
    """
    global _item_url_iter
    _item_url_iter = iter(FAKE_ITEM_URLS)

    template_result = await test_db.execute(
        select(PlanTemplate).where(
            PlanTemplate.name == "套图生成",
            PlanTemplate.is_builtin == True,
        )
    )
    radiate_template = template_result.scalar_one_or_none()
    assert radiate_template is not None, "Built-in 套图生成 template must exist"
    template_id = radiate_template.id

    mocker.patch(
        "app.utils.image_client.ImageClient.generate",
        new_callable=AsyncMock,
        return_value={"data": [{"url": "https://fake.test/anchor_grid.png"}]},
    )
    mocker.patch(
        "app.utils.image_client.ImageClient.extract_images",
        return_value=["https://fake.test/anchor_grid.png"],
    )
    mocker.patch(
        "app.utils.image_client.ImageClient.chat_edit",
        new_callable=AsyncMock,
        return_value={
            "choices": [
                {"message": {"images": [{"image_url": {"url": "https://fake.test/item.png"}}]}}
            ]
        },
    )
    mocker.patch(
        "app.utils.image_client.ImageClient.extract_images_from_chat",
        side_effect=_next_item_url,
    )
    mocker.patch(
        "app.services.generate_service._crop_grid",
        new_callable=AsyncMock,
        return_value=FAKE_CELL_B64,
    )

    rounds = build_mock_llm_rounds([
        [
            {
                "id": "call_t3_1",
                "type": "function",
                "function": {
                    "name": "plan",
                    "arguments": json.dumps({
                        "action": "apply",
                        "template_id": template_id,
                        "variables": {
                            "items": [
                                {"prompt": "an orange cat with happy expression"},
                                {"prompt": "an orange cat with sad expression"},
                                {"prompt": "an orange cat with angry expression"},
                                {"prompt": "an orange cat with surprised expression"},
                                {"prompt": "an orange cat sleeping"},
                                {"prompt": "an orange cat eating"},
                            ],
                            "style": "cute emoji sticker style, orange tabby cat character",
                            "overall_theme": "orange cat emoticon set",
                        },
                    }),
                },
            },
        ],
        [],  # round 2: no tool_calls → radiate takeover in handle_agent_generate
    ])
    mocker.patch("app.services.agent_service.LLMClient.chat_stream_with_tools", new=rounds)

    result = await handle_agent_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="帮我生成一套6个表情包，主角是一只橘猫，包含开心、难过、愤怒、惊讶、睡觉、吃饭",
            agent_mode=True,
            agent_tools=[],
        ),
    )

    assert result.get("strategy") == "radiate", "T3 should use radiate strategy"
    assert result.get("cancelled") == False
    assert "images" in result

    images = result["images"]
    assert len(images) >= 7, (
        f"T3 should have 1 anchor + 6 items = 7 images, got {len(images)}"
    )

    radiate_steps = [
        s for s in result.get("steps", [])
        if s.get("type") in ("radiate", "radiate_item")
    ]
    assert len(radiate_steps) >= 7, (
        f"T3 should have radiate steps (1 grid + 6 items), got {len(radiate_steps)}"
    )

    plan_tool_calls = [
        s for s in result.get("steps", [])
        if s.get("name") == "plan" and s.get("type") == "tool_call"
    ]
    assert len(plan_tool_calls) >= 1, "T3 should call plan (apply) at least once"
