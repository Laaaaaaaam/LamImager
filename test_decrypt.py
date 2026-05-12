import sys
sys.path.insert(0, "e:/LamImager/backend")
from app.utils.crypto import decrypt
import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()
c.execute("SELECT nickname, api_key_enc FROM api_providers")
rows = c.fetchall()
for r in rows:
    try:
        key = decrypt(r[1])
        print(f"{r[0]}: decrypt OK, key ends with ...{key[-4:]}")
    except Exception as e:
        print(f"{r[0]}: decrypt FAILED: {e}")
conn.close()
