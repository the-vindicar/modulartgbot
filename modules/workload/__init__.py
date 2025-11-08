"""Разбор файла с нагрузкой и его приведение к более удобному виду."""
import dataclasses

from sqlalchemy.ext.asyncio import AsyncEngine
from aiogram import Dispatcher

from api import CoreAPI
from .tg import context
from .timeplan_parsing import TimePlanParser
from .models import WorkloadRepository

__all__ = []
requires = [AsyncEngine, Dispatcher]
provides = []


@dataclasses.dataclass
class WorkloadConfig:
    """Конфигурация модуля."""
    timeplan_url: str = 'https://kosgos.ru/external/op_info.php'


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    cfg = await api.config.load('workload', WorkloadConfig)
    engine = await api(AsyncEngine)
    context.timeplan_parser = TimePlanParser(cfg.timeplan_url)
    context.repository = WorkloadRepository(engine)
    await context.repository.create_tables()
    dispatcher = await api(Dispatcher)
    dispatcher.include_router(context.router)
    if context.template_path.is_file():
        context.log.info('Workload table processor started.')
    else:
        context.log.error('Workload table processor: template file not found!')
    yield
