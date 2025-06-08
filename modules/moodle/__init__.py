import dataclasses
import logging
import os
import zoneinfo

from ._classes import *
from ._moodle import Moodle
from ._errors import MoodleError

from api import CoreAPI


__all__ = [
    'Moodle', 'MoodleError',
    'user_id', 'course_id', 'assignment_id', 'group_id', 'role_id', 'submission_id',
    'User', 'Group', 'Role', 'Course', 'Participant', 'Assignment', 'Submission', 'SubmittedFile'
]
requires = []
provides = [Moodle]


async def lifetime(api: CoreAPI):
    @dataclasses.dataclass
    class MoodleConfig:
        base_url: str
        user: str
        pwd: str = None
        timezone: str = 'Europe/Moscow'

    log = logging.getLogger(name=f'modules.moodle')

    cfg = await api.config.load('moodle', MoodleConfig)
    moodle = Moodle(cfg.base_url, cfg.user, os.getenv('MOODLE_PWD', cfg.pwd), log=log)
    moodle.timezone = zoneinfo.ZoneInfo(cfg.timezone)
    async with moodle:
        try:
            await moodle.login()
        except Exception:
            log.error('Failed to connect to moodle instance at %s as %s',
                      moodle.base_url, cfg.user, exc_info=True)
            raise
        else:
            log.info('Connected to moodle instance at %s as %s',
                     moodle.base_url, cfg.user)

        async def provider() -> Moodle:
            return moodle

        api.register_api_provider(provider, Moodle)
        yield
        log.info('Disconnected from moodle instance at %s', moodle.base_url)
