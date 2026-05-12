import sys
sys.path.insert(0, "e:/LamImager/backend")
from app.utils.crypto import decrypt
import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()

c.execute("SELECT id, name, base_url, api_key_enc FROM api_vendors")
rows = c.fetchall()
for r in rows:
    try:
        key = decrypt(r[3])
        print(f"Vendor {r[1]}: base_url={r[2]}, key=****{key[-4:]}, OK")
    except Exception as e:
        print(f"Vendor {r[1]}: base_url={r[2]}, DECRYPT FAILED ({type(e).__name__})")

c.execute("SELECT nickname, base_url, api_key_enc, vendor_id FROM api_providers")
rows = c.fetchall()
for r in rows:
    try:
        key = decrypt(r[2])
        print(f"Provider {r[0]}: base_url={r[1]}, vendor_id={r[3]}, key=****{key[-4:]}, OK")
    except Exception as e:
        print(f"Provider {r[0]}: base_url={r[1]}, vendor_id={r[3]}, DECRYPT FAILED ({type(e).__name__})")

conn.close()
