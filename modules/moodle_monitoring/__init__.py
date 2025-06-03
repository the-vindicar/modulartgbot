import logging

import asyncpg
import orm1

from api import CoreAPI
from modules.moodle import Moodle
from ._config import MoodleMonitorConfig
from ._moodle_classes import *
from ._data_layer import *


requires = [asyncpg.Pool, orm1.SessionBackend, Moodle]
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
