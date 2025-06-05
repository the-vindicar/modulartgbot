import logging

import asyncpg

from api import CoreAPI
from modules.moodle import Moodle
from ._config import MoodleMonitorConfig
from .data_layer import *


requires = [asyncpg.Pool, Moodle]
provides = []


async def lifetime(api: CoreAPI):
    log = logging.getLogger('modules.moodlemon')
    cfg = await api.config.load('moodle_monitor', MoodleMonitorConfig)
    dbpool = await api(asyncpg.Pool)
    async with dbpool.acquire() as connection:
        connection: asyncpg.Connection
        async with connection.transaction():
            await create_tables(connection)
        yield
