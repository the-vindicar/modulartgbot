"""Разбор файла с нагрузкой и его приведение к более удобному виду."""
import asyncio
import dataclasses

from sqlalchemy.ext.asyncio import AsyncEngine
from aiogram import Dispatcher

from api import CoreAPI, background_task
from .tg import context
from .timeplan_parsing import TimePlanParser
from .models import WorkloadRepository

__all__ = []
requires = [AsyncEngine, Dispatcher]
provides = []


@dataclasses.dataclass
class WorkloadConfig:
    """Конфигурация модуля."""
    timeplan_url: str = ''
    timeplan_update_days: int = 7
    timeplan_specialty_codes: list[str] = dataclasses.field(default_factory=list)


async def parse_timeplan(cfg: WorkloadConfig) -> None:
    """Периодически обновляет графики работы."""
    if not cfg.timeplan_url or cfg.timeplan_update_days < 1 or not cfg.timeplan_specialty_codes:
        context.log.warning('Settings for timeplan parsing make updates impossible.')
        while True:
            await asyncio.sleep(24*60*60)
    else:
        timeplan_parser = TimePlanParser(cfg.timeplan_url)
        while True:
            context.log.debug('Updating time plans for: %s', ', '.join(cfg.timeplan_specialty_codes))
            try:
                async for plan in timeplan_parser.acquire_plans_for(cfg.timeplan_specialty_codes):
                    context.log.debug('  Found plan for group %s', plan.group_code)
                    await context.repository.store_timeplan(plan)
            except Exception as err:
                context.log.error('Failed to update timeplans!', exc_info=err)
            await asyncio.sleep(cfg.timeplan_update_days*24*60*60)


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    cfg = await api.config.load('workload', WorkloadConfig)
    engine = await api(AsyncEngine)
    context.repository = WorkloadRepository(engine)
    await context.repository.create_tables()
    dispatcher = await api(Dispatcher)
    dispatcher.include_router(context.router)
    if context.template_path.is_file():
        context.log.info('Workload table processor started.')
    else:
        context.log.error('Workload table processor: template file not found!')
    async with background_task(parse_timeplan(cfg)):
        yield
