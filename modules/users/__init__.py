"""Поддерживает список пользователей системы, а также механизм одноразовых кодов."""
import logging

from sqlalchemy.ext.asyncio import AsyncEngine
from aiogram import Bot, Dispatcher

from api import CoreAPI
from .models import UserBase, SiteUser, UserRepository, UserRoles
from .tg import context, router, is_registered, is_site_admin


__all__ = ['SiteUser', 'UserRepository', 'UserRoles', 'is_registered', 'is_site_admin']
requires = [AsyncEngine, Bot, Dispatcher]
provides = [UserRepository]


async def lifetime(api: CoreAPI):
    """Тело модуля."""
    log = logging.getLogger('modules.users')
    engine = await api(AsyncEngine)
    context.log = log
    context.bot = await api(Bot)
    context.dispatcher = await api(Dispatcher)
    context.repository = UserRepository(engine)
    api.register_api_provider(context.repository, UserRepository)

    async with engine.connect() as conn:
        await conn.run_sync(UserBase.metadata.create_all)
    yield
