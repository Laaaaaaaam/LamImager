import asyncio
import sys
sys.path.insert(0, "e:/LamImager/backend")

async def main():
    from app.database import async_session
    from sqlalchemy import select, func
    from app.models.api_provider import ApiProvider, ApiVendor

    async with async_session() as session:
        providers = (await session.execute(
            select(ApiProvider).where(ApiProvider.vendor_id.is_(None))
        )).scalars().all()

        print(f"Providers without vendor_id: {len(providers)}")
        for p in providers:
            print(f"  {p.nickname}: base_url='{p.base_url}', key_enc_len={len(p.api_key_enc) if p.api_key_enc else 0}")

        vendor_count = (await session.execute(select(func.count(ApiVendor.id)))).scalar()
        print(f"Existing vendors: {vendor_count}")

        base_url_groups = {}
        for p in providers:
            base_url = (p.base_url or "").strip()
            if base_url:
                base_url_groups.setdefault(base_url, []).append(p)

        print(f"\nBase URL groups: {len(base_url_groups)}")
        for url, group in base_url_groups.items():
            print(f"  {url}: {len(group)} providers")
            for p in group:
                print(f"    {p.nickname}: api_key_enc={'yes' if p.api_key_enc else 'no'}")

asyncio.run(main())
