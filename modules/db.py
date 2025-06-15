import typing as t
import os
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine, AsyncSession

from api import CoreAPI

requires = []
provides = [AsyncEngine, AsyncSession, ]


async def lifetime(api: CoreAPI) -> t.AsyncGenerator:
    host = os.environ['POSTGRES_HOST']
    user = os.environ['POSTGRES_USER']
    pwd = os.environ['POSTGRES_PWD']
    dbname = os.environ['POSTGRES_DB']
    is_temp_database = os.environ.get('TEMP_DATABASE', 'no').lower() in ('yes', '1', 'true')
    dsn = f'postgresql+asyncpg://{user}:{pwd}@{host}/{dbname}'
    log = logging.getLogger('modules.db')
    log.info('Connecting to database...')
    engine = create_async_engine(dsn)
    session_maker = async_sessionmaker(bind=engine, )
    log.info('Connected successfuly to %s@%s', dbname, host)
    if is_temp_database:
        log.warning('Database is configured as temporary, all tables will be dropped on exit!')

    async def engine_provider() -> AsyncEngine:
        return engine

    async def session_provider() -> AsyncSession:
        return session_maker()

    api.register_api_provider(engine_provider, AsyncEngine)
    api.register_api_provider(session_provider, AsyncSession)
    yield
    if is_temp_database:
        log.warning('Database is configured as temporary, dropping all tables!')
        async with engine.connect() as conn:
            await conn.execute(text('''
                DO $$ DECLARE
                    r RECORD;
                BEGIN
                    -- if the schema you operate on is not "current", you will want to
                    -- replace current_schema() in query with 'schematodeletetablesfrom'
                    -- *and* update the generate 'DROP...' accordingly.
                    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = current_schema()) LOOP
                        EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                    END LOOP;
                END $$;
            '''))
    log.info('Disconnected from database.')
