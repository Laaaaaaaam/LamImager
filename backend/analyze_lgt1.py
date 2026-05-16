import asyncio, json
from sqlalchemy import text, select
from app.database import async_session
from app.models.message import Message

async def main():
    async with async_session() as db:
        r = await db.execute(text("SELECT id, name FROM sessions WHERE id LIKE '%lgt1%' OR name LIKE '%lgt1%'"))
        rows = r.fetchall()
        if not rows:
            print("No session found matching lgt1")
            return
        sid = rows[0][0]
        print(f"session: id={rows[0][0]}, name={rows[0][1]}")
        
        r2 = await db.execute(select(Message).where(Message.session_id == sid).order_by(Message.created_at))
        msgs = r2.scalars().all()
        for m in msgs:
            meta = m.metadata_ or {}
            print(f"\n  role={m.role.value} type={m.message_type.value}")
            print(f"  content={m.content[:100]}")
            
            intent = meta.get("intent", {})
            if intent:
                print(f"  intent: type={intent.get('task_type')} confidence={intent.get('confidence')} items={len(intent.get('items',[]))}")
                dt = intent.get("decision_trace", {})
                if dt:
                    print(f"  intent_source: {dt.get('source')}")
            
            plan = meta.get("plan", {})
            if plan:
                print(f"  plan: strategy={plan.get('strategy')} steps={len(plan.get('steps',[]))}")
                for s in plan.get("steps", []):
                    print(f"    step{s.get('index')}: {s.get('description','')[:60]} | {s.get('prompt','')[:60]}")
            
            critic = meta.get("critic", {})
            if critic:
                print(f"  critic: avg={critic.get('avg_score')} results={len(critic.get('results',[]))}")
                for r in critic.get("results", []):
                    print(f"    score={r.get('score')} issues={r.get('issues',[])}")
            
            decision = meta.get("decision")
            if decision:
                print(f"  decision: {decision}")
            
            trace = meta.get("node_trace", [])
            if trace:
                nodes = []
                for t in trace:
                    n = t.get("node","?")
                    extra = ""
                    if t.get("strategy"): extra = f"({t['strategy']},{t.get('steps')}st)"
                    elif t.get("avg_score"): extra = f"(avg={t['avg_score']})"
                    elif t.get("result"): extra = f"({t['result']})"
                    nodes.append(f"{n}{extra}")
                print(f"  trace: {' -> '.join(nodes)}")
            
            tokens_in = meta.get("tokens_in", 0)
            tokens_out = meta.get("tokens_out", 0)
            cost = meta.get("cost", 0)
            print(f"  tokens: in={tokens_in} out={tokens_out} cost={cost:.4f}")
            
            imgs = meta.get("images", [])
            if imgs:
                print(f"  images: {len(imgs)} urls")

asyncio.run(main())
