"""Отслеживает изменения на сервере Moodle и кэширует их в локальной БД для использования другими модулями."""
import logging

from sqlalchemy.ext.asyncio import AsyncEngine
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from api import CoreAPI, background_task
from modules.moodle import MoodleAdapter
from modules.users import tg_is_site_admin
from ._config import MoodleMonitorConfig
from ._scheduler import Scheduler
from .models import *


__all__ = [
    'MoodleRepository',
    'MoodleCourse', 'MoodleGroup', 'MoodleRole', 'MoodleUser',
    'MoodleParticipant', 'MoodleParticipantGroups', 'MoodleParticipantRoles',
    'MoodleAssignment', 'MoodleSubmission', 'MoodleSubmittedFile'
]
requires = [AsyncEngine, MoodleAdapter, Bot, Dispatcher]
provides = [MoodleRepository]


tgrouter = Router(name='users_extra')

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

    @tgrouter.message(tg_is_site_admin, Command('moodle_scan_now'))
    async def force_moodle_scan(msg: Message):
        """Принудительно запускает сканирование СДО на предмет новых ответов на задания."""
        scheduler.wakeup.set()
        log.info('User %s ( %s ) forced a scan.', msg.from_user.full_name, msg.from_user.id)
        await msg.answer('Сканирование СДО запущено.')

    dispatcher = await api(Dispatcher)
    dispatcher.include_router(tgrouter)

    async with background_task(scheduler.scheduler_task()):
        yield
