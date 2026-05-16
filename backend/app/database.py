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
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='api_vendors'"))
        if not result.fetchone():
            await conn.execute(text("""
                CREATE TABLE api_vendors (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    base_url VARCHAR(500) NOT NULL,
                    api_key_enc TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))

        result = await conn.execute(text("PRAGMA table_info('api_providers')"))
        columns = [row[1] for row in result.fetchall()]
        if "vendor_id" not in columns:
            await conn.execute(text("ALTER TABLE api_providers ADD COLUMN vendor_id VARCHAR(36)"))

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

        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='plan_templates'"))
        if result.fetchone():
            result = await conn.execute(text("PRAGMA table_info('plan_templates')"))
            pt_columns = [row[1] for row in result.fetchall()]
            if "builtin_version" not in pt_columns:
                await conn.execute(text("ALTER TABLE plan_templates ADD COLUMN builtin_version INTEGER DEFAULT 0"))

        result = await conn.execute(text("PRAGMA table_info('skills')"))
        skill_columns = [row[1] for row in result.fetchall()]
        if "strategy" not in skill_columns:
            await conn.execute(text("ALTER TABLE skills ADD COLUMN strategy VARCHAR(20) DEFAULT ''"))
        if "steps" not in skill_columns:
            await conn.execute(text("ALTER TABLE skills ADD COLUMN steps JSON DEFAULT '[]'"))
        if "strategy_hint" not in skill_columns:
            await conn.execute(text("ALTER TABLE skills ADD COLUMN strategy_hint VARCHAR(20) DEFAULT ''"))
        if "planning_bias" not in skill_columns:
            await conn.execute(text("ALTER TABLE skills ADD COLUMN planning_bias JSON DEFAULT '{}'"))
        if "constraints" not in skill_columns:
            await conn.execute(text("ALTER TABLE skills ADD COLUMN constraints JSON DEFAULT '{}'"))
        if "prompt_bias" not in skill_columns:
            await conn.execute(text("ALTER TABLE skills ADD COLUMN prompt_bias JSON DEFAULT '{}'"))

    async with async_session() as session:
        from app.services.plan_template_service import seed_builtin_templates
        await seed_builtin_templates(session)

        from app.services.api_manager import migrate_providers_to_vendors
        await migrate_providers_to_vendors(session)
