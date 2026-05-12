import sys
sys.path.insert(0, "e:/LamImager/backend")
import base64
import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()
c.execute("SELECT nickname, api_key_enc FROM api_providers")
rows = c.fetchall()
for r in rows:
    name, enc = r
    print(f"\n{name}:")
    print(f"  enc length: {len(enc)}")
    try:
        raw = base64.b64decode(enc)
        print(f"  raw length: {len(raw)}")
        print(f"  nonce (12 bytes): {raw[:12].hex()}")
        print(f"  ciphertext+tag length: {len(raw) - 12}")
    except Exception as e:
        print(f"  base64 decode FAILED: {e}")
conn.close()
