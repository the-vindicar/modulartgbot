"""Предоставляет обёртку для доступа к серверу Moodle."""
import datetime
import dataclasses
import logging
import os
import zoneinfo

from ._classes import *
from ._adapter import MoodleAdapter
from ._messagebot import MoodleMessageBot
from .moodle import *

from api import CoreAPI, PostInit, background_task


__all__ = [
    'MoodleAdapter', 'MoodleMessageBot', 'MoodleError',
    'MessageType', 'ConvType', 'MessageReadStatus', 'SendMessage', 'SendInstantMessage', 'RMessage',
    'user_id', 'course_id', 'assignment_id', 'group_id', 'role_id', 'submission_id',
    'User', 'Group', 'Role', 'Course', 'Participant', 'Assignment', 'Submission', 'SubmittedFile'
]
requires = []
provides = [MoodleAdapter, MoodleMessageBot]


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    @dataclasses.dataclass
    class MoodleConfig:
        """Конфигурация связи с сервером Moodle."""
        base_url: str = None
        user: str = None
        pwd: str = None
        timezone: str = 'Europe/Moscow'
        message_poll_seconds: int = 15

    log = logging.getLogger(name=f'modules.moodle')

    cfg = await api.config.load('moodle', MoodleConfig)
    moodle_instance = MoodleAdapter(os.getenv('MOODLE_URL', cfg.base_url),
                                    os.getenv('MOODLE_USER', cfg.user),
                                    os.getenv('MOODLE_PWD', cfg.pwd),
                                    log=log)
    moodle_instance.timezone = zoneinfo.ZoneInfo(cfg.timezone)
    async with moodle_instance:
        try:
            await moodle_instance.login()
        except Exception:
            log.error('Failed to connect to moodle instance at %s as %s',
                      moodle_instance.base_url, cfg.user, exc_info=True)
            raise
        else:
            log.info('Connected to moodle instance at %s as %s',
                     moodle_instance.base_url, cfg.user)
        api.register_api_provider(moodle_instance, MoodleAdapter)
        message_bot = MoodleMessageBot(moodle_instance, log)
        api.register_api_provider(message_bot, MoodleMessageBot)
        yield PostInit

        if cfg.message_poll_seconds > 0:
            async with background_task(message_bot.poll_messages(datetime.timedelta(seconds=cfg.message_poll_seconds))):
                yield
        else:  # не выполняем поллинг сообщений
            yield

        log.info('Disconnected from moodle instance at %s', moodle_instance.base_url)
