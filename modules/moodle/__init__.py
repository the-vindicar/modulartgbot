import dataclasses
import logging
import os

from ._moodle import Moodle
from ._errors import MoodleError

from api import CoreAPI


__all__ = ['Moodle', 'MoodleError']
requires = []
provides = [Moodle]


async def lifetime(api: CoreAPI):
    @dataclasses.dataclass
    class MoodleConfig:
        base_url: str
        user: str
        pwd: str = None

    log = logging.getLogger(name=f'modules.moodle')

    cfg = await api.config.load('moodle', MoodleConfig)
    moodle = Moodle(cfg.base_url, cfg.user, os.getenv('MOODLE_PWD', cfg.pwd), log=log)
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
