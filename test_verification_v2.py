import asyncio
import json
import time
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
    async with httpx.AsyncClient(timeout=600) as client:
        resp = await client.post(f"{BASE_URL}/sessions/{session_id}/generate", json=payload)
        resp.raise_for_status()
        return resp.json()

async def collect_sse_events(session_id: str, duration: int = 10) -> list:
    events = []
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=duration + 5) as client:
            async with client.stream("GET", f"{BASE_URL}/sessions/events", timeout=duration) as resp:
                async for line in resp.aiter_lines():
                    if time.time() - start > duration:
                        break
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:])
                            payload = data.get("payload", {})
                            if payload.get("session_id") == session_id or data.get("correlation_id", "").endswith(session_id):
                                events.append(data)
                        except json.JSONDecodeError:
                            pass
    except (httpx.ReadTimeout, httpx.ConnectTimeout):
        pass
    return events

async def run_test(test_id: str, prompt: str, image_count: int = 1, expect_task_type: str = "", expect_strategy: str = ""):
    print(f"\n{'='*70}")
    print(f"测试编号: {test_id}")
    print(f"输入指令: {prompt}")
    print(f"{'='*70}")

    session_id = await create_session(f"verify-{test_id}")

    # Start SSE collection in background
    sse_task = asyncio.create_task(collect_sse_events(session_id, duration=30))

    # Small delay to ensure SSE subscription is ready
    await asyncio.sleep(0.5)

    try:
        result = await agent_generate(session_id, prompt, image_count)
    except Exception as e:
        print(f"  API 异常: {e}")
        sse_task.cancel()
        return {
            "test_id": test_id,
            "prompt": prompt,
            "task_type": "EXCEPTION",
            "strategy": "EXCEPTION",
            "steps_summary": str(e),
            "images_count": 0,
            "final_images_count": 0,
            "intermediate_images_count": 0,
            "checkpoint_triggered": False,
            "pass": False,
            "remark": f"API异常: {e}",
        }

    # Collect SSE events
    try:
        sse_events = await asyncio.wait_for(sse_task, timeout=5)
    except asyncio.TimeoutError:
        sse_events = []

    # Extract data from result
    error = result.get("error")
    intent = result.get("intent", {})
    task_type = intent.get("task_type", "")
    strategy = intent.get("strategy", "")
    expected_count = intent.get("expected_count", 0)
    items = intent.get("items", [])
    images = result.get("images", [])
    final_images = result.get("final_images", [])
    intermediate_images = result.get("intermediate_images", [])
    steps = result.get("steps", [])

    # Check checkpoint from SSE events
    checkpoint_triggered = False
    checkpoint_events = []
    for evt in sse_events:
        evt_type = evt.get("event_type", "")
        payload = evt.get("payload", {})
        ptype = payload.get("type", "")
        if evt_type == "checkpoint_required" or ptype == "agent_checkpoint":
            checkpoint_triggered = True
            checkpoint_events.append({
                "event_type": evt_type,
                "payload_type": ptype,
                "step": payload.get("step", ""),
            })

    # Also check messages for checkpoint info
    messages = await get_session_messages(session_id)
    agent_msg = None
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("message_type") == "agent":
            agent_msg = msg
            break

    agent_meta = agent_msg.get("metadata", {}) if agent_msg else {}
    agent_intent = agent_meta.get("intent", {}) if agent_meta else {}

    # Build steps summary
    steps_summary = []
    for i, s in enumerate(steps):
        s_type = s.get("type", "")
        if s_type == "direct_generate":
            steps_summary.append(f"[{i}] direct_generate")
        elif s_type == "prompt_generation":
            steps_summary.append(f"[{i}] prompt_generation ({len(s.get('prompts', []))} prompts)")
        elif s_type == "tool_result":
            steps_summary.append(f"[{i}] tool_result: {s.get('name', '')} item={s.get('item_id', s.get('label', ''))} status={s.get('status', '')}")
        elif s_type == "radiate":
            steps_summary.append(f"[{i}] radiate: items={s.get('items', 0)} grid={s.get('grid', '')}")
        elif s_type == "radiate_item":
            steps_summary.append(f"[{i}] radiate_item: idx={s.get('index', '')}")
        elif "step_index" in s:
            steps_summary.append(f"[{i}] step_{s['step_index']}: images={len(s.get('images', []))}")
        else:
            steps_summary.append(f"[{i}] {s_type or json.dumps(s, ensure_ascii=False)[:60]}")

    # Determine pass/fail
    passed = True
    remark_parts = []

    if error:
        remark_parts.append(f"错误: {error}")
        passed = False

    if expect_task_type and task_type != expect_task_type:
        remark_parts.append(f"类型不匹配: 期望={expect_task_type}, 实际={task_type}")
        passed = False

    if expect_strategy and strategy != expect_strategy:
        remark_parts.append(f"策略不匹配: 期望={expect_strategy}, 实际={strategy}")
        passed = False

    if not error and len(images) == 0:
        remark_parts.append("无图片结果")
        passed = False

    # Print results in the required template format
    print(f"\n1. intent.task_type = {task_type}")
    print(f"2. strategy = {strategy}")
    print(f"3. steps 摘要 =")
    for s in steps_summary:
        print(f"     {s}")
    print(f"4. images 数量 = {len(images)}")
    print(f"5. final_images 数量 = {len(final_images)}")
    print(f"6. intermediate_images 数量 = {len(intermediate_images)}")
    print(f"7. 是否触发 checkpoint = {checkpoint_triggered}")
    if checkpoint_events:
        for ce in checkpoint_events:
            print(f"     checkpoint event: {ce}")
    print(f"8. 最终是否符合预期 = {'PASS' if passed else 'FAIL'}")

    if remark_parts:
        print(f"\n备注: {'; '.join(remark_parts)}")

    # Extra details
    print(f"\n--- 额外信息 ---")
    print(f"  expected_count: {expected_count}")
    print(f"  items count: {len(items)}")
    if items:
        for it in items[:6]:
            print(f"    item: id={it.get('id','')}, label={it.get('label','')}, hint={it.get('prompt_hint','')[:40]}")
    print(f"  agent_msg intent: task_type={agent_intent.get('task_type','')}, strategy={agent_intent.get('strategy','')}")
    print(f"  agent_msg images: {len(agent_meta.get('images', []))}")
    print(f"  agent_msg final_images: {len(agent_meta.get('final_images', []))}")

    return {
        "test_id": test_id,
        "prompt": prompt,
        "task_type": task_type,
        "strategy": strategy,
        "steps_summary": steps_summary,
        "images_count": len(images),
        "final_images_count": len(final_images),
        "intermediate_images_count": len(intermediate_images),
        "checkpoint_triggered": checkpoint_triggered,
        "checkpoint_events": checkpoint_events,
        "pass": passed,
        "remark": "; ".join(remark_parts) if remark_parts else "",
        "expected_count": expected_count,
        "items_count": len(items),
    }

async def main():
    results = []

    # V1: single
    results.append(await run_test(
        "V1", "画一只猫", image_count=1,
        expect_task_type="single", expect_strategy="single",
    ))

    # V2: multi_independent
    results.append(await run_test(
        "V2", "给我3张不同风格的logo方案", image_count=3,
        expect_task_type="multi_independent", expect_strategy="parallel",
    ))

    # V3: iterative
    results.append(await run_test(
        "V3", "结合一下这两个logo的设计，生成一个新logo，再细化优化", image_count=1,
        expect_task_type="iterative", expect_strategy="iterative",
    ))

    # V4: radiate
    results.append(await run_test(
        "V4", "做一套4个橘猫表情包，包含开心、生气、惊讶、害羞", image_count=4,
        expect_task_type="radiate", expect_strategy="radiate",
    ))

    # V5: radiate 统一风格
    results.append(await run_test(
        "V5", "做一组统一风格四张图，主题是同一个角色在春夏秋冬四个场景里", image_count=4,
        expect_task_type="radiate", expect_strategy="radiate",
    ))

    # V6: checkpoint (same prompt as V4, focus on checkpoint)
    results.append(await run_test(
        "V6", "做一套4个橘猫表情包，包含开心、生气、惊讶、害羞", image_count=4,
        expect_task_type="radiate", expect_strategy="radiate",
    ))

    # V7: single should NOT trigger checkpoint
    results.append(await run_test(
        "V7", "画一只猫", image_count=1,
        expect_task_type="single", expect_strategy="single",
    ))

    # Summary
    print("\n\n" + "=" * 70)
    print("总体验证结果汇总")
    print("=" * 70)
    for r in results:
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  {r['test_id']}: {status} | type={r['task_type']}, strategy={r['strategy']}, images={r['images_count']}, final={r['final_images_count']}, intermediate={r['intermediate_images_count']}, checkpoint={r['checkpoint_triggered']}")
        if r["remark"]:
            print(f"         备注: {r['remark']}")

    print(f"\n总计: {sum(1 for r in results if r['pass'])}/{len(results)} 通过")

if __name__ == "__main__":
    asyncio.run(main())
