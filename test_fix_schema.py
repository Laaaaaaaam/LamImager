import sqlite3

conn = sqlite3.connect("e:/LamImager/data/lamimager.db")
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='api_vendors'")
if not c.fetchone():
    c.execute("""
        CREATE TABLE api_vendors (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            base_url VARCHAR(500) NOT NULL,
            api_key_enc TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("Created api_vendors table")
else:
    print("api_vendors table already exists")

c.execute("PRAGMA table_info('api_providers')")
columns = [row[1] for row in c.fetchall()]
if "vendor_id" not in columns:
    c.execute("ALTER TABLE api_providers ADD COLUMN vendor_id VARCHAR(36)")
    print("Added vendor_id column to api_providers")
else:
    print("vendor_id column already exists in api_providers")

conn.commit()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"\nAll tables: {tables}")

c.execute("SELECT id, nickname, vendor_id FROM api_providers")
rows = c.fetchall()
print(f"\nProviders:")
for r in rows:
    print(f"  {r[0][:8]} {r[1]} vendor_id={r[2]}")

conn.close()
