import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()
c.execute("SELECT nickname, base_url, api_key_enc, vendor_id FROM api_providers")
rows = c.fetchall()
for r in rows:
    print(f"  {r[0]}: base_url='{r[1]}', key_enc_len={len(r[2]) if r[2] else 0}, vendor_id={r[3]}")
conn.close()
