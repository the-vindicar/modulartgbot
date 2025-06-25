"""Предоставляет доступ к базе данных через посредничество асинхронного варианта SQLAlchemy."""
import typing as t
import os
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from api import CoreAPI

requires = []
provides = [AsyncEngine]


async def lifetime(api: CoreAPI) -> t.AsyncGenerator:
    """Тело модуля."""
    host = os.environ['POSTGRES_HOST']
    user = os.environ['POSTGRES_USER']
    pwd = os.environ['POSTGRES_PWD']
    dbname = os.environ['POSTGRES_DB']
    is_temp_database = os.environ.get('TEMP_DATABASE', 'no').lower() in ('yes', '1', 'true')
    dsn = f'postgresql+asyncpg://{user}:{pwd}@{host}/{dbname}'
    log = logging.getLogger('modules.db')
    log.info('Connecting to database...')
    engine = create_async_engine(dsn)
    log.info('Connected successfuly to %s@%s', dbname, host)
    if is_temp_database:
        log.warning('Database is configured as temporary, all tables will be dropped on exit!')

    api.register_api_provider(engine, AsyncEngine)
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
