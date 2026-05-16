import sqlite3, json

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
conn.row_factory = sqlite3.Row

cur = conn.execute("SELECT id, title, status, created_at, updated_at FROM sessions WHERE title LIKE '%卡%' OR title LIKE '%stuck%'")
sessions = cur.fetchall()
if not sessions:
    cur = conn.execute("SELECT id, title, status, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 20")
    sessions = cur.fetchall()
    print("No '卡住了' session found. Showing recent sessions:")
    for s in sessions:
        print(f"  {s['id']} | {s['title']} | status={s['status']} | updated={s['updated_at']}")
else:
    for s in sessions:
        print(f"Session: {s['id']} | {s['title']} | status={s['status']} | created={s['created_at']} | updated={s['updated_at']}")

    sid = sessions[0]["id"]
    print(f"\n--- Messages for session {sid} ---")
    cur = conn.execute(
        "SELECT id, message_type, content, created_at, metadata FROM messages WHERE session_id = ? ORDER BY created_at ASC",
        (sid,),
    )
    msgs = cur.fetchall()
    for m in msgs:
        meta = m["metadata"] or ""
        content = (m["content"] or "")[:150]
        print(f"  {m['created_at']} | {m['message_type']} | {content}")
        if meta:
            try:
                md = json.loads(meta)
                print(f"    META: {json.dumps(md, ensure_ascii=False)[:200]}")
            except:
                print(f"    META(raw): {meta[:200]}")

conn.close()