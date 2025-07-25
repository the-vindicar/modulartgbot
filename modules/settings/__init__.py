"""Предоставляет единый механизм хранения настроек с привязкой к отдельным сущностям."""
from sqlalchemy.ext.asyncio import AsyncEngine

from api import CoreAPI
from .models import SettingsRepository


__all__ = ['SettingsRepository']
requires = [AsyncEngine]
provides = [SettingsRepository]


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    engine = await api(AsyncEngine)
    repo = SettingsRepository(engine)
    await repo.create_tables()
    api.register_api_provider(repo, SettingsRepository)
    yield
