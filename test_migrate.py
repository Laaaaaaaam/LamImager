import asyncio
import sys
sys.path.insert(0, "e:/LamImager/backend")

async def main():
    from app.database import async_session
    from app.services.api_manager import migrate_providers_to_vendors

    async with async_session() as session:
        await migrate_providers_to_vendors(session)

    import sqlite3
    conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
    c = conn.cursor()

    c.execute("SELECT id, name, base_url FROM api_vendors")
    rows = c.fetchall()
    print(f"Vendors ({len(rows)}):")
    for r in rows:
        print(f"  {r[0][:8]} {r[1]} base_url={r[2]}")

    c.execute("SELECT id, nickname, vendor_id FROM api_providers")
    rows = c.fetchall()
    print(f"\nProviders:")
    for r in rows:
        print(f"  {r[0][:8]} {r[1]} vendor_id={r[2]}")

    conn.close()

asyncio.run(main())
