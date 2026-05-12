import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"Tables: {tables}")

if "api_vendors" in tables:
    c.execute("SELECT id, name, base_url, provider_type FROM api_vendors")
    rows = c.fetchall()
    print(f"\nVendors ({len(rows)}):")
    for r in rows:
        print(f"  {r}")

conn.close()
