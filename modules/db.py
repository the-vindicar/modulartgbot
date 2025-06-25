"""Предоставляет доступ к базе данных через посредничество асинхронного варианта SQLAlchemy."""
import typing as t
import os
import logging

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
    dsn = f'postgresql+asyncpg://{user}:{pwd}@{host}/{dbname}'
    log = logging.getLogger('modules.db')
    log.info('Connecting to database...')
    engine = create_async_engine(dsn)
    log.info('Connected successfuly to %s@%s', dbname, host)
    api.register_api_provider(engine, AsyncEngine)
    yield
    log.info('Disconnected from database.')
