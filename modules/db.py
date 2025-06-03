import typing as t
import os
import logging

import asyncpg

from api import CoreAPI

requires = []
provides = [asyncpg.Pool]


async def lifetime(api: CoreAPI) -> t.AsyncGenerator:
    host = os.environ['POSTGRES_HOST']
    user = os.environ['POSTGRES_USER']
    pwd = os.environ['POSTGRES_PWD']
    dbname = os.environ['POSTGRES_DB']
    dsn = f'postgresql://{user}:{pwd}@{host}/{dbname}'
    log = logging.getLogger('modules.db')
    log.info('Connecting to database...')
    async with asyncpg.create_pool(dsn) as pool:
        log.info('Connected successfuly to %s@%s', dbname, host)

        async def pool_provider() -> asyncpg.Pool:
            return pool

        api.register_api_provider(pool_provider, asyncpg.Pool)
        yield
    log.info('Disconnected from database.')
