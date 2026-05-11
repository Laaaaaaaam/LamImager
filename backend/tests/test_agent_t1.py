from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.session import GenerateRequest
from app.services.generate_service import handle_agent_generate

from .conftest import build_mock_llm_rounds


@pytest.mark.asyncio
async def test_single_image_direct_generation(
    test_db: AsyncSession,
    llm_provider,
    image_provider,
    test_session,
    mocker,
):
    """
    T1: 生成一张赛博朋克风格的城市夜景
    Agent 直接调用 generate_image，不调用 plan，1 轮结束。
    """
    mocker.patch(
        "app.services.generate_service.generate_images_core",
        new_callable=AsyncMock,
        return_value=(["https://fake.test/cyberpunk_city.png"], 0, 0),
    )

    rounds = build_mock_llm_rounds([
        [
            {
                "id": "call_t1_1",
                "type": "function",
                "function": {
                    "name": "generate_image",
                    "arguments": json.dumps({
                        "prompt": "cyberpunk city night scene, neon lights, rain-slicked streets, futuristic dystopia",
                        "count": 1,
                    }),
                },
            },
        ],
        [],  # round 2: no tool_calls → loop breaks
    ])
    mocker.patch("app.services.agent_service.LLMClient.chat_stream_with_tools", new=rounds)

    result = await handle_agent_generate(
        test_db,
        GenerateRequest(
            session_id=test_session.id,
            prompt="生成一张赛博朋克风格的城市夜景",
            agent_mode=True,
            agent_tools=[],
        ),
    )

    assert result.get("cancelled") == False
    assert "images" in result
    assert "cyberpunk_city" in str(result["images"])

    plan_calls = [
        s for s in result.get("steps", [])
        if s.get("name") == "plan" and s.get("type") == "tool_call"
    ]
    assert len(plan_calls) == 0, "T1 should NOT call plan"

    gen_calls = [
        s for s in result.get("steps", [])
        if s.get("name") == "generate_image"
    ]
    assert len(gen_calls) >= 1, "T1 should call generate_image at least once"
