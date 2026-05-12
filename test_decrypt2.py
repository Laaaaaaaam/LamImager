import sys
sys.path.insert(0, "e:/LamImager/backend")
from app.utils.crypto import decrypt, encrypt
import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()
c.execute("SELECT id, nickname, api_key_enc FROM api_providers")
rows = c.fetchall()

for r in rows:
    pid, name, enc = r
    try:
        key = decrypt(enc)
        print(f"{name}: decrypt OK, key=****{key[-4:]}")
    except Exception as e:
        print(f"{name}: decrypt FAILED: {type(e).__name__}: {e}")

# Test encrypt/decrypt roundtrip
test = encrypt("test_key_12345")
result = decrypt(test)
print(f"\nRoundtrip test: {'OK' if result == 'test_key_12345' else 'FAIL'}")

conn.close()
