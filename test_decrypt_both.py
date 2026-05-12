import sys
sys.path.insert(0, "e:/LamImager/backend")
from app.utils.crypto import decrypt
import sqlite3

for db_path in ["e:/LamImager/data/lamimager.db", "e:/LamImager/data/lamimager.db.bak"]:
    print(f"\n=== {db_path} ===")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT nickname, api_key_enc FROM api_providers")
        rows = c.fetchall()
        for r in rows:
            try:
                key = decrypt(r[1])
                print(f"  {r[0]}: OK, key=****{key[-4:]}")
            except Exception as e:
                print(f"  {r[0]}: FAILED ({type(e).__name__})")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")
