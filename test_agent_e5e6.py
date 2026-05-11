import asyncio
import json
import time
import httpx

BASE_URL = "http://127.0.0.1:8000/api"

async def create_session(title: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BASE_URL}/sessions", json={"title": title})
        resp.raise_for_status()
        data = resp.json()
        return data["id"]

async def get_session_messages(session_id: str) -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}/sessions/{session_id}/messages")
        resp.raise_for_status()
        return resp.json()

async def agent_generate(session_id: str, prompt: str, image_count: int = 1) -> dict:
    payload = {
        "prompt": prompt,
        "image_count": image_count,
        "agent_mode": True,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{BASE_URL}/sessions/{session_id}/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

async def run_experiment(name: str, prompt: str, image_count: int = 1, expect_task_type: str = ""):
    print(f"\n{'='*60}")
    print(f"实验: {name}")
    print(f"输入: prompt='{prompt}', image_count={image_count}")
    print(f"预期任务类型: {expect_task_type}")
    print(f"{'='*60}")

    session_id = await create_session(f"test-{name}")
    print(f"创建会话: {session_id[:8]}...")

    try:
        result = await agent_generate(session_id, prompt, image_count)
        print(f"\n--- API 直接返回 ---")
        print(f"  error: {result.get('error', 'None')}")
        intent = result.get('intent', {})
        print(f"  intent: task_type={intent.get('task_type', 'N/A')}, strategy={intent.get('strategy', 'N/A')}")
        print(f"  expected_count: {intent.get('expected_count', 'N/A')}")
        print(f"  items count: {len(intent.get('items', []))}")
        print(f"  images count: {len(result.get('images', []))}")
        print(f"  final_images count: {len(result.get('final_images', []))}")
        print(f"  steps count: {len(result.get('steps', []))}")
        print(f"  output: {result.get('output', 'N/A')[:200]}")
        if result.get('steps'):
            for i, step in enumerate(result['steps'][:5]):
                print(f"  step[{i}]: {json.dumps(step, ensure_ascii=False)[:150]}")

        messages = await get_session_messages(session_id)
        print(f"\n--- 会话消息 ({len(messages)} 条) ---")
        for msg in messages:
            role = msg.get('role', '?')
            mtype = msg.get('message_type', '?')
            content = msg.get('content', '')[:100]
            meta = msg.get('metadata', {})
            if role == 'system' and mtype == 'agent':
                intent_info = meta.get('intent', {})
                print(f"  [{role}/{mtype}] task_type={intent_info.get('task_type','?')}, strategy={intent_info.get('strategy','?')}")
                print(f"    images={len(meta.get('images',[]))}, final_images={len(meta.get('final_images',[]))}")
                print(f"    output: {meta.get('final_output','')[:150]}")
            elif role == 'system' and mtype == 'error':
                print(f"  [{role}/{mtype}] {content}")
            elif role == 'system' and mtype == 'image':
                urls = meta.get('image_urls', [])
                print(f"  [{role}/{mtype}] {len(urls)} images")
            else:
                print(f"  [{role}/{mtype}] {content}")

        actual_task_type = intent.get('task_type', '')
        type_match = actual_task_type == expect_task_type if expect_task_type else True
        has_images = len(result.get('images', [])) > 0
        has_error = bool(result.get('error'))

        status = "PASS" if type_match and (has_images or has_error) else "FAIL"
        if not type_match:
            status = f"TYPE_MISMATCH (expected={expect_task_type}, actual={actual_task_type})"
        elif not has_images and not has_error:
            status = "NO_RESULT"

        print(f"\n--- 判定: {status} ---")
        return {"name": name, "status": status, "result": result, "session_id": session_id}

    except Exception as e:
        print(f"\n--- 异常: {e} ---")
        import traceback
        traceback.print_exc()
        return {"name": name, "status": f"EXCEPTION: {e}", "result": {}, "session_id": session_id}

async def main():
    results = []

    # E5: Search + Generate
    results.append(await run_experiment(
        "E5-search-style",
        "参考最近流行的UI风格做一个首页",
        image_count=1,
        expect_task_type="single",
    ))

    results.append(await run_experiment(
        "E5-search-nordic",
        "找一些北欧风参考图，再生成卧室效果图",
        image_count=1,
        expect_task_type="single",
    ))

    # E6: Error handling
    # Test with no provider - we can't easily remove providers, so test with invalid prompt patterns
    results.append(await run_experiment(
        "E6-error-ambiguous",
        "",  # empty prompt
        image_count=1,
        expect_task_type="single",
    ))

    print("\n\n" + "=" * 60)
    print("实验5-6 结果汇总")
    print("=" * 60)
    for r in results:
        print(f"  {r['name']}: {r['status']}")

if __name__ == "__main__":
    asyncio.run(main())
