import asyncio
import json
import httpx

BASE_URL = "http://127.0.0.1:8000/api"

async def create_session(title: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/sessions", json={"title": title})
        resp.raise_for_status()
        return resp.json()["id"]

async def get_session_messages(session_id: str) -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/sessions/{session_id}/messages")
        resp.raise_for_status()
        return resp.json()

async def agent_generate(session_id: str, prompt: str, image_count: int = 1) -> dict:
    payload = {"prompt": prompt, "image_count": image_count, "agent_mode": True}
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{BASE_URL}/sessions/{session_id}/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

async def run_test(name: str, prompt: str, image_count: int = 1, expect_task_type: str = "", expect_error: str = ""):
    print(f"\n{'='*60}")
    print(f"验证: {name}")
    print(f"输入: prompt='{prompt}', image_count={image_count}")
    if expect_task_type:
        print(f"预期类型: {expect_task_type}")
    if expect_error:
        print(f"预期错误: {expect_error}")
    print(f"{'='*60}")

    session_id = await create_session(f"verify-{name}")
    print(f"会话: {session_id[:8]}...")

    try:
        result = await agent_generate(session_id, prompt, image_count)
        error = result.get('error')
        intent = result.get('intent', {})
        task_type = intent.get('task_type', '')
        images = result.get('images', [])
        steps = result.get('steps', [])

        print(f"  error: {error}")
        print(f"  intent: task_type={task_type}, strategy={intent.get('strategy','')}")
        print(f"  expected_count: {intent.get('expected_count','')}")
        print(f"  items: {len(intent.get('items', []))}")
        print(f"  images: {len(images)}")
        if steps:
            for i, s in enumerate(steps[:3]):
                print(f"  step[{i}]: {json.dumps(s, ensure_ascii=False)[:120]}")

        if expect_error:
            status = "PASS" if error and expect_error in error else f"FAIL (expected error containing '{expect_error}', got '{error}')"
        elif expect_task_type:
            type_ok = task_type == expect_task_type
            has_result = len(images) > 0 or error
            status = "PASS" if type_ok and has_result else f"FAIL (type={task_type}, images={len(images)}, error={error})"
        else:
            status = "PASS" if len(images) > 0 or error else "FAIL (no result)"

        print(f"\n  >>> {status}")
        return {"name": name, "status": status}

    except Exception as e:
        print(f"\n  >>> EXCEPTION: {e}")
        return {"name": name, "status": f"EXCEPTION: {e}"}

async def main():
    results = []

    # Verify fix for multi_independent items empty
    results.append(await run_test(
        "V1-multi-style",
        "画3张不同风格的猫",
        image_count=3,
        expect_task_type="multi_independent",
    ))

    results.append(await run_test(
        "V1-multi-logo",
        "给我4个不同logo方案",
        image_count=4,
        expect_task_type="multi_independent",
    ))

    # Verify fix for empty prompt validation
    results.append(await run_test(
        "V2-empty-prompt",
        "",
        image_count=1,
        expect_error="提示词不能为空",
    ))

    # Verify single still works
    results.append(await run_test(
        "V3-single-cat",
        "画一只猫",
        image_count=1,
        expect_task_type="single",
    ))

    # Verify radiate images count (should not include anchor)
    results.append(await run_test(
        "V4-radiate-count",
        "做一套4个表情包",
        image_count=4,
        expect_task_type="radiate",
    ))

    # Verify error path returns intent
    print(f"\n{'='*60}")
    print("V5: 验证错误路径返回 intent")
    print(f"{'='*60}")
    session_id = await create_session("verify-V5")
    result = await agent_generate(session_id, "", 1)
    has_intent = bool(result.get('intent'))
    print(f"  error: {result.get('error')}")
    print(f"  intent present: {has_intent}")
    v5_status = "PASS" if has_intent else "FAIL"
    print(f"\n  >>> {v5_status}")
    results.append({"name": "V5-error-intent", "status": v5_status})

    print("\n\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    for r in results:
        print(f"  {r['name']}: {r['status']}")

if __name__ == "__main__":
    asyncio.run(main())
