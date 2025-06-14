import typing as t
import os
import logging

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine, AsyncSession

from api import CoreAPI

requires = []
provides = [AsyncEngine, AsyncSession, ]


async def lifetime(api: CoreAPI) -> t.AsyncGenerator:
    host = os.environ['POSTGRES_HOST']
    user = os.environ['POSTGRES_USER']
    pwd = os.environ['POSTGRES_PWD']
    dbname = os.environ['POSTGRES_DB']
    dsn = f'postgresql+asyncpg://{user}:{pwd}@{host}/{dbname}'
    log = logging.getLogger('modules.db')
    log.info('Connecting to database...')
    engine = create_async_engine(dsn)
    session_maker = async_sessionmaker(bind=engine, )
    log.info('Connected successfuly to %s@%s', dbname, host)

    async def engine_provider() -> AsyncEngine:
        return engine

    async def session_provider() -> AsyncSession:
        return session_maker()

    api.register_api_provider(engine_provider, AsyncEngine)
    api.register_api_provider(session_provider, AsyncSession)
    yield
    log.info('Disconnected from database.')
