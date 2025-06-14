"""Поддерживает список пользователей системы."""
import logging

import asyncpg

from api import CoreAPI


requires = [asyncpg.Pool]
provides = []


async def lifetime(api: CoreAPI):
    log = logging.getLogger('modules.users')
    pool = await api(asyncpg.Pool)

    async with pool.acquire() as conn:
        yield
