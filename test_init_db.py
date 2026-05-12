import asyncio
import sys
sys.path.insert(0, "e:/LamImager/backend")

async def main():
    from app.database import init_db
    await init_db()
    print("init_db() completed")

    import sqlite3
    conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print(f"Tables: {tables}")

    if "api_vendors" in tables:
        c.execute("SELECT id, name, base_url FROM api_vendors")
        rows = c.fetchall()
        print(f"Vendors ({len(rows)}):")
        for r in rows:
            print(f"  {r}")

    c.execute("SELECT id, nickname, vendor_id FROM api_providers")
    rows = c.fetchall()
    print(f"\nProviders:")
    for r in rows:
        print(f"  {r[0][:8]} {r[1]} vendor_id={r[2]}")

    conn.close()

asyncio.run(main())
