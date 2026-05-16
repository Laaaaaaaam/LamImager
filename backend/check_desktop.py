import sqlite3, json, os

appdata = os.environ.get("APPDATA", "")
db_path = os.path.join(appdata, "LamImager", "lamimager.db")
print(f"Desktop DB path: {db_path}")
print(f"Exists: {os.path.exists(db_path)}")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cur = conn.execute("SELECT id, title, status, created_at, updated_at FROM sessions WHERE title LIKE '%卡%' ORDER BY updated_at DESC")
    sessions = cur.fetchall()
    if not sessions:
        print("No '卡住了' session found, showing recent:")
        cur = conn.execute("SELECT id, title, status, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT 5")
        sessions = cur.fetchall()

    for s in sessions:
        print(f"  {s['id']} | {s['title']} | status={s['status']} | updated={s['updated_at']}")

    if sessions:
        sid = sessions[0]["id"]
        print(f"\n--- Messages for '{sessions[0]['title']}' ({sid}) ---")
        cur = conn.execute(
            "SELECT id, message_type, content, created_at, metadata FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (sid,),
        )
        msgs = cur.fetchall()
        for m in msgs:
            content = (m["content"] or "")[:200]
            print(f"  {m['created_at']} | {m['message_type']} | {content}")
            meta = m["metadata"] or ""
            if meta:
                try:
                    md = json.loads(meta)
                    if md:
                        print(f"    META: {json.dumps(md, ensure_ascii=False)[:300]}")
                except:
                    pass

    conn.close()
