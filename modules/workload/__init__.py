"""Разбор файла с нагрузкой и его приведение к более удобному виду."""
from aiogram import Dispatcher

from api import CoreAPI

from .tg import router, log, template_path


__all__ = []
requires = [Dispatcher]
provides = []


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    dispatcher = await api(Dispatcher)
    dispatcher.include_router(router)
    if template_path.is_file():
        log.info('Workload table processor started.')
    else:
        log.error('Workload table processor: template file not found!')
    yield
