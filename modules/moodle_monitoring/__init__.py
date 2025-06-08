import logging

import asyncpg

from api import CoreAPI, background_task
from modules.moodle import Moodle
from ._config import MoodleMonitorConfig
from ._scheduler import Scheduler
from ._data_layer import create_tables


requires = [asyncpg.Pool, Moodle]
provides = []


async def lifetime(api: CoreAPI):
    log = logging.getLogger('modules.moodlemon')
    cfg = await api.config.load('moodle_monitor', MoodleMonitorConfig)
    dbpool = await api(asyncpg.Pool)
    moodle = await api(Moodle)
    async with dbpool.acquire() as connection:
        connection: asyncpg.Connection
        async with connection.transaction():
            await create_tables(connection)
        scheduler = Scheduler(cfg, log, moodle, connection)
        async with background_task(scheduler.scheduler_task()):
            yield
