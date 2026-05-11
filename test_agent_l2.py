import asyncio
import json
import time
import sys
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

async def wait_for_task_complete(session_id: str, timeout: int = 240) -> dict:
    start = time.time()
    last_event_id = None
    async with httpx.AsyncClient(timeout=timeout + 30) as client:
        while time.time() - start < timeout:
            try:
                headers = {}
                if last_event_id:
                    headers["Last-Event-ID"] = last_event_id
                async with client.stream("GET", f"{BASE_URL}/sessions/events", headers=headers, timeout=30) as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("id:"):
                            last_event_id = line[3:].strip()
                        elif line.startswith("data:"):
                            try:
                                data = json.loads(line[5:])
                                payload = data.get("payload", {})
                                if payload.get("session_id") == session_id or data.get("correlation_id", "").endswith(session_id):
                                    event_type = data.get("event_type", "")
                                    ptype = payload.get("type", "")
                                    if event_type == "task_completed" or ptype == "agent_done":
                                        return {"status": "completed", "data": data}
                                    elif event_type == "task_failed" or ptype == "agent_error":
                                        return {"status": "failed", "data": data}
                                    elif ptype == "agent_cancelled":
                                        return {"status": "cancelled", "data": data}
                            except json.JSONDecodeError:
                                pass
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                continue
            await asyncio.sleep(1)
    return {"status": "timeout", "data": {}}

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
        print(f"  intent: task_type={result.get('intent', {}).get('task_type', 'N/A')}, strategy={result.get('intent', {}).get('strategy', 'N/A')}")
        print(f"  expected_count: {result.get('intent', {}).get('expected_count', 'N/A')}")
        print(f"  images count: {len(result.get('images', []))}")
        print(f"  final_images count: {len(result.get('final_images', []))}")
        print(f"  steps count: {len(result.get('steps', []))}")
        print(f"  output: {result.get('output', 'N/A')[:200]}")
        if result.get('steps'):
            for i, step in enumerate(result['steps']):
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

        actual_task_type = result.get('intent', {}).get('task_type', '')
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
        return {"name": name, "status": f"EXCEPTION: {e}", "result": {}, "session_id": session_id}

async def main():
    results = []

    results.append(await run_experiment(
        "E1-single-cat",
        "画一只猫",
        image_count=1,
        expect_task_type="single",
    ))

    results.append(await run_experiment(
        "E1-single-logo",
        "做一个科技风logo",
        image_count=1,
        expect_task_type="single",
    ))

    results.append(await run_experiment(
        "E2-multi-style",
        "画3张不同风格的猫",
        image_count=3,
        expect_task_type="multi_independent",
    ))

    results.append(await run_experiment(
        "E2-multi-logo",
        "给我4个不同logo方案",
        image_count=4,
        expect_task_type="multi_independent",
    ))

    results.append(await run_experiment(
        "E2-multi-views",
        "分别画正面、侧面、背面",
        image_count=3,
        expect_task_type="multi_independent",
    ))

    results.append(await run_experiment(
        "E3-iterative-refine",
        "先出草图，再精修",
        image_count=1,
        expect_task_type="iterative",
    ))

    results.append(await run_experiment(
        "E3-iterative-logo",
        "先做一个基础logo，再细化质感",
        image_count=1,
        expect_task_type="iterative",
    ))

    results.append(await run_experiment(
        "E4-radiate-emoji",
        "做一套6个橘猫表情包",
        image_count=6,
        expect_task_type="radiate",
    ))

    results.append(await run_experiment(
        "E4-radiate-set",
        "统一风格四张插画",
        image_count=4,
        expect_task_type="radiate",
    ))

    results.append(await run_experiment(
        "E4-radiate-character",
        "同一角色四个动作",
        image_count=4,
        expect_task_type="radiate",
    ))

    results.append(await run_experiment(
        "E4-radiate-icons",
        "做一组图标",
        image_count=1,
        expect_task_type="radiate",
    ))

    print("\n\n" + "=" * 60)
    print("实验结果汇总")
    print("=" * 60)
    for r in results:
        print(f"  {r['name']}: {r['status']}")

if __name__ == "__main__":
    asyncio.run(main())
