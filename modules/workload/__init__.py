"""Разбор файла с нагрузкой и его приведение к более удобному виду."""
from aiogram import Dispatcher

from api import CoreAPI

from .tg import router


__all__ = []
requires = [Dispatcher]
provides = []


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    dispatcher = await api(Dispatcher)
    dispatcher.include_router(router)
    yield
