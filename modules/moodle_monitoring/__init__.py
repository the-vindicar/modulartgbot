"""Отслеживает изменения на сервере Moodle и кэширует их в локальной БД для использования другими модулями."""
import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from api import CoreAPI, background_task
from modules.moodle import MoodleAdapter
from ._config import MoodleMonitorConfig
from ._scheduler import Scheduler
from .datalayer import *


__all__ = [
    'MoodleRepository',
    'MoodleCourse', 'MoodleGroup', 'MoodleRole', 'MoodleUser',
    'MoodleParticipant', 'MoodleParticipantGroups', 'MoodleParticipantRoles',
    'MoodleAssignment', 'MoodleSubmission', 'MoodleSubmittedFile'
]
requires = [AsyncEngine, MoodleAdapter]
provides = [MoodleRepository]


async def lifetime(api: CoreAPI):
    """Контекст работы модуля мониторинга Moodle. Код до yield инициализирует работу, после - завершает."""
    log = logging.getLogger('modules.moodlemon')
    cfg = await api.config.load('moodle_monitoring', MoodleMonitorConfig)
    engine = await api(AsyncEngine)
    moodle = await api(MoodleAdapter)
    repo = MoodleRepository(engine, log)
    await repo.create_tables()
    api.register_api_provider(repo, MoodleRepository)

    scheduler = Scheduler(cfg, log, moodle, repo)
    async with background_task(scheduler.scheduler_task()):
        yield
