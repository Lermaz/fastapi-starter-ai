from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(s: Settings) -> dict:
    kwargs: dict = {"echo": s.db_echo}
    if "sqlite" in s.database_url.lower():
        return kwargs
    kwargs["pool_size"] = s.db_pool_size
    kwargs["max_overflow"] = s.db_max_overflow
    kwargs["pool_recycle"] = s.db_pool_recycle_seconds
    kwargs["pool_pre_ping"] = s.db_pool_pre_ping
    return kwargs


engine = create_async_engine(settings.database_url, **_engine_kwargs(settings))

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
