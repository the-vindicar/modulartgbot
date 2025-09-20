"""Отслеживает поступающие сведения о новых файлах, анализирует их и сравнивает между собой."""
import logging

import quart
from sqlalchemy.ext.asyncio import AsyncEngine

from api import CoreAPI, background_task
from modules.moodle import MoodleAdapter
from modules.file_comparison.digests.config import FileComparisonConfig
from ._scheduler import scheduler
from ._web import blueprint, context
from .models import FileDataRepository


__all__ = []
requires = [quart.Quart, AsyncEngine, MoodleAdapter]
provides = [FileDataRepository]


async def lifetime(api: CoreAPI):
    """Контекст работы модуля сравнения файлов в Moodle. Код до yield инициализирует работу, после - завершает."""
    log = logging.getLogger('modules.filecomp')
    cfg = await api.config.load('file_comparison', FileComparisonConfig)
    engine = await api(AsyncEngine)
    m = await api(MoodleAdapter)
    repo = FileDataRepository(engine, log)
    await repo.create_tables()

    context.log = log
    context.repository = repo

    api.register_api_provider(repo, FileDataRepository)
    api.register_web_router(blueprint)
    async with background_task(scheduler(log, cfg, repo, m)):
        yield
