import asyncio
import httpx

async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post("http://127.0.0.1:8000/api/sessions", json={"title": "v5-test"})
        sid = r.json()["id"]
        r2 = await c.post(f"http://127.0.0.1:8000/api/sessions/{sid}/generate", json={"prompt": "", "image_count": 1, "agent_mode": True})
        d = r2.json()
        print(f"error: {d.get('error')}")
        print(f"intent: {d.get('intent')}")
        print("PASS" if d.get("intent") else "FAIL")

asyncio.run(main())
