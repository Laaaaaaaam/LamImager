import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()

c.execute("SELECT id, name, base_url, length(api_key_enc) FROM api_vendors")
rows = c.fetchall()
print(f"Vendors ({len(rows)}):")
for r in rows:
    print(f"  {r[0][:8]} {r[1]} base_url={r[2]} key_len={r[3]}")

c.execute("SELECT nickname, vendor_id FROM api_providers")
rows = c.fetchall()
print(f"\nProviders:")
for r in rows:
    print(f"  {r[0]} vendor_id={r[1]}")

conn.close()
