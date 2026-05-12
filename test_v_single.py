import asyncio
import json
import httpx
import sys

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
    async with httpx.AsyncClient(timeout=900) as client:
        resp = await client.post(f"{BASE_URL}/sessions/{session_id}/generate", json=payload)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}", "images": [], "steps": [], "intent": {}}
        return resp.json()

async def run_test(test_id: str, prompt: str, image_count: int = 1, expect_task_type: str = "", expect_strategy: str = ""):
    print(f"\n{'='*70}")
    print(f"测试编号: {test_id}")
    print(f"输入指令: {prompt}")
    print(f"{'='*70}")

    session_id = await create_session(f"verify-{test_id}")

    try:
        result = await agent_generate(session_id, prompt, image_count)
    except Exception as e:
        print(f"  API 异常: {type(e).__name__}: {str(e)[:200]}")
        return {"test_id": test_id, "task_type": "EXCEPTION", "strategy": "EXCEPTION",
                "steps_summary": [], "images_count": 0, "final_images_count": 0,
                "intermediate_images_count": 0, "pass": False,
                "remark": f"API异常: {type(e).__name__}: {str(e)[:100]}"}

    error = result.get("error")
    intent = result.get("intent", {})
    task_type = intent.get("task_type", "")
    strategy = intent.get("strategy", "")
    images = result.get("images", [])
    final_images = result.get("final_images", [])
    intermediate_images = result.get("intermediate_images", [])
    steps = result.get("steps", [])

    steps_summary = []
    for i, s in enumerate(steps):
        s_type = s.get("type", "")
        if s_type == "direct_generate":
            steps_summary.append(f"[{i}] direct_generate")
        elif s_type == "prompt_generation":
            steps_summary.append(f"[{i}] prompt_generation ({len(s.get('prompts', []))} prompts)")
        elif s_type == "tool_result":
            steps_summary.append(f"[{i}] tool_result: {s.get('name','')} item={s.get('item_id',s.get('label',''))} status={s.get('status','')}")
        elif s_type == "radiate":
            steps_summary.append(f"[{i}] radiate: items={s.get('items',0)} grid={s.get('grid','')}")
        elif s_type == "radiate_item":
            steps_summary.append(f"[{i}] radiate_item: idx={s.get('index','')}")
        elif "step_index" in s:
            steps_summary.append(f"[{i}] step_{s['step_index']}: images={len(s.get('images',[]))}")
        else:
            steps_summary.append(f"[{i}] {s_type or json.dumps(s, ensure_ascii=False)[:60]}")

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

    print(f"\n1. intent.task_type = {task_type}")
    print(f"2. strategy = {strategy}")
    print(f"3. steps 摘要 =")
    for s in steps_summary:
        print(f"     {s}")
    print(f"4. images 数量 = {len(images)}")
    print(f"5. final_images 数量 = {len(final_images)}")
    print(f"6. intermediate_images 数量 = {len(intermediate_images)}")
    print(f"7. 是否触发 checkpoint = (see SSE)")
    print(f"8. 最终是否符合预期 = {'PASS' if passed else 'FAIL'}")
    if remark_parts:
        print(f"\n备注: {'; '.join(remark_parts)}")

    return {"test_id": test_id, "task_type": task_type, "strategy": strategy,
            "steps_summary": steps_summary, "images_count": len(images),
            "final_images_count": len(final_images),
            "intermediate_images_count": len(intermediate_images),
            "pass": passed, "remark": "; ".join(remark_parts) if remark_parts else ""}

async def main():
    test_id = sys.argv[1] if len(sys.argv) > 1 else "V1"

    tests = {
        "V1": ("画一只猫", 1, "single", "single"),
        "V2": ("给我3张不同风格的logo方案", 3, "multi_independent", "parallel"),
        "V3": ("结合一下这两个logo的设计，生成一个新logo，再细化优化", 1, "iterative", "iterative"),
        "V4": ("做一套4个橘猫表情包，包含开心、生气、惊讶、害羞", 4, "radiate", "radiate"),
        "V5": ("做一组统一风格四张图，主题是同一个角色在春夏秋冬四个场景里", 4, "radiate", "radiate"),
        "V6": ("做一套4个橘猫表情包，包含开心、生气、惊讶、害羞", 4, "radiate", "radiate"),
        "V7": ("画一只猫", 1, "single", "single"),
    }

    if test_id == "ALL":
        results = []
        for tid, (prompt, count, etype, estrat) in tests.items():
            r = await run_test(tid, prompt, count, etype, estrat)
            results.append(r)

        print("\n\n" + "=" * 70)
        print("总体验证结果汇总")
        print("=" * 70)
        for r in results:
            status = "PASS" if r["pass"] else "FAIL"
            print(f"  {r['test_id']}: {status} | type={r['task_type']}, strategy={r['strategy']}, images={r['images_count']}, final={r['final_images_count']}, intermediate={r['intermediate_images_count']}")
            if r["remark"]:
                print(f"         备注: {r['remark']}")
        print(f"\n总计: {sum(1 for r in results if r['pass'])}/{len(results)} 通过")
    else:
        prompt, count, etype, estrat = tests[test_id]
        await run_test(test_id, prompt, count, etype, estrat)

if __name__ == "__main__":
    asyncio.run(main())
