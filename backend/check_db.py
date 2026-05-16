import sqlite3, json

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
conn.row_factory = sqlite3.Row

cur = conn.execute("SELECT id, title, status, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 5")
sessions = cur.fetchall()
for s in sessions:
    print(f"Session: {s['id']} | {s['title']} | status={s['status']} | updated={s['updated_at']}")

if sessions:
    sid = sessions[0]["id"]
    print(f"\n--- Latest session messages ({sid}) ---")
    cur = conn.execute(
        "SELECT id, message_type, content, created_at, metadata FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT 15",
        (sid,),
    )
    msgs = cur.fetchall()
    for m in msgs:
        meta = m["metadata"] or ""
        content = (m["content"] or "")[:120]
        print(f"  {m['created_at']} | {m['message_type']} | {content}")
        if meta:
            try:
                md = json.loads(meta)
                if "agent_mode" in md or "search_type" in md or "task_type" in md or "error" in md:
                    print(f"    META: {json.dumps(md, ensure_ascii=False)[:200]}")
            except:
                pass

conn.close()
