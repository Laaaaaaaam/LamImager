import asyncio, traceback
from app.database import async_session, init_db
from app.services.generate_service import handle_agent_generate
from app.services.session_manager import create_session
from app.schemas.session import GenerateRequest, SessionCreate

async def main():
    await init_db()
    async with async_session() as db:
        session = await create_session(db, SessionCreate(title="test6-mc-emoji"))
        sid = session.id
        print(f"Session: {sid}")
        data = GenerateRequest(
            session_id=sid,
            prompt="生成一套MC风格的表情包，需要开心、难过、生气、惊讶4种表情",
            agent_mode=True,
            agent_tools=["generate_image", "plan", "web_search", "image_search"],
            image_count=1,
        )
        try:
            result = await handle_agent_generate(db, data)
            print(f"\n=== RESULTS ===")
            print(f"STEPS: {len(result.get('steps', []))}")
            for s in result.get('steps', []):
                name = s.get('name', '?')
                content = s.get('content', '')[:100]
                print(f"  {s['type']}: {name} | {content}")
            print(f"CANCELLED: {result.get('cancelled')}")
            print(f"COST: {result.get('cost')}")
            output = result.get('output', '')[:300]
            print(f"OUTPUT: {output}")
        except Exception as e:
            print(f"\n!!! ERROR !!!")
            print(f"{type(e).__name__}: {e}")
            traceback.print_exc()

asyncio.run(main())
