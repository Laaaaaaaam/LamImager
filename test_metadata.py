import sys
sys.path.insert(0, "e:/LamImager/backend")
from app.database import Base
from app.models import ApiVendor, ApiProvider

print("Tables in Base.metadata:")
for name in sorted(Base.metadata.tables.keys()):
    print(f"  {name}")

print(f"\nApiVendor tablename: {ApiVendor.__tablename__}")
print(f"ApiProvider tablename: {ApiProvider.__tablename__}")
