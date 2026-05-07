from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import settings

engine = create_async_engine(
    settings.DB_URL,
    echo=settings.DEBUG,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info('billing_records')"))
        columns = [row[1] for row in result.fetchall()]
        if "session_id" not in columns:
            await conn.execute(text("ALTER TABLE billing_records ADD COLUMN session_id VARCHAR(36)"))

        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"))
        if result.fetchone():
            await conn.execute(text("UPDATE billing_records SET session_id = task_id WHERE session_id IS NULL AND task_id IS NOT NULL"))

        await conn.execute(text("DROP TABLE IF EXISTS sub_tasks"))
        await conn.execute(text("DROP TABLE IF EXISTS tasks"))

        result = await conn.execute(text("PRAGMA table_info('sessions')"))
        columns = [row[1] for row in result.fetchall()]
        if "status" not in columns:
            await conn.execute(text("ALTER TABLE sessions ADD COLUMN status VARCHAR(20) DEFAULT 'idle' NOT NULL"))

        await conn.execute(text("UPDATE sessions SET status = 'idle' WHERE status != 'idle'"))

    async with async_session() as session:
        from app.services.plan_template_service import seed_builtin_templates
        await seed_builtin_templates(session)
