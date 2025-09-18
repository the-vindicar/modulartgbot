"""Отслеживает поступающие сведения о новых файлах, анализирует их и сравнивает между собой."""
import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from api import CoreAPI, background_task
from modules.moodle import MoodleAdapter
from modules.file_comparison.digests.config import FileComparisonConfig
from ._scheduler import scheduler
from .models import FileDataRepository


__all__ = []
requires = [AsyncEngine, MoodleAdapter]
provides = [FileDataRepository]


async def lifetime(api: CoreAPI):
    """Контекст работы модуля сравнения файлов в Moodle. Код до yield инициализирует работу, после - завершает."""
    log = logging.getLogger('modules.filecomp')
    cfg = await api.config.load('file_comparison', FileComparisonConfig)
    engine = await api(AsyncEngine)
    m = await api(MoodleAdapter)
    repo = FileDataRepository(engine, log)
    await repo.create_tables()
    api.register_api_provider(repo, FileDataRepository)
    async with background_task(scheduler(log, cfg, repo, m)):
        yield
