import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"All tables: {tables}")

if "api_vendors" in tables:
    c.execute("SELECT id, name, base_url, is_active FROM api_vendors")
    rows = c.fetchall()
    print(f"\nVendors ({len(rows)}):")
    for r in rows:
        print(f"  {r}")

    c.execute("SELECT id, nickname, vendor_id FROM api_providers")
    rows = c.fetchall()
    print(f"\nProviders vendor_id:")
    for r in rows:
        print(f"  {r[0][:8]} {r[1]} vendor_id={r[2]}")
else:
    print("\napi_vendors table NOT found!")

conn.close()
